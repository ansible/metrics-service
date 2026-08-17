# Gamification — Architecture Notes

Implementation architecture for the gamification feature. See [sdp.md](./sdp.md) for the System Design Plan.

## Architecture Overview

**Hourly computation task:**

1. Load all jobs from DB for last 30 days
2. Compute statistics for global leaderboard, orgs and users
3. Store global leaderboard as 1 row in key-value table in jsonb
4. Store each user result as 1 row in key-value table in jsonb
5. Store each org result as 1 row in key-value table in jsonb

**API request flow:**

1. Load global leaderboard row, 1 row for the requesting user, N rows for each org the user belongs to
2. Merge into one JSON and send response to client

## Missing data

We are missing users reference in some job types - for example scheduled ones.

There needs to be investigation if we are not missing any other job types.


## Gamification design

### Hourly computation

- hourly task will compute all the statistics at once for last 30 days. If the task fails, the data are not stored - tasks have their own retry system. If all retries fails, user will see info that we has either no data, or timestamp of last successfull computation.

- The collector loads **all jobs with terminal status** (`successful`, `failed`, `error`) from `dashboard_job_data` for the last 30 days. Most gamification metrics only use successful jobs, but the "Reliable" badge requires knowing about failures — it awards users who ran 20+ consecutive successful jobs with no failures or errors in between. Without failed/error jobs in the dataset, we cannot detect intervening failures and the badge would be uncomputable.

- SQL over 30 days should take about several seconds for largest customers (5000 jobs per hour, 2000 users, 100 orgs)
Its loading from one table - the query is simple and its reading all the data, because we need all the data. The SQL does not require any joins, everything is encoded in the jobs table already.

- Then computation of metrics for orgs is fine, it can be slow for users, but overall estimation is up to 1 minute total including SQL load and save

### Storage

- Data will be saved in key/value table (needs migration) - each

- There will be several rows that will get overwritten per each hourly computation:

  gamification_global - all data that all users will see, will contain top 10 for each critera - all orgs and users order for each criteria

  gamification_user_{user_id} - all data for 1 user - its ranking and potential additional stats for every criteria - there will be as much rows as there are users

  gamification_org_{org_id} - the same as users, but for 1 org

  The key/value table will have:
  key (string) - unique key
  value (jsonb) - contains the precomputed JSON blob
  created, modified timestamp

  This table can be then reused for any future data storage we need

### Precomputed data structures

  So the hourly task will compute statistics and store it in these tables. The Overall json will look like this:

  #### Part 1: Global data (key: `gamification_global`)

  ```json
  {
      "computed_at": "2026-08-14T09:00:00Z",

      "enterprise_streak": {
          "days": 28,
          "milestones": [7, 14]
      },

      "calendar_grid": [
          {"date": "2026-07-16", "enterprise_active": true},
          {"date": "2026-07-17", "enterprise_active": true},
          {"date": "2026-08-14", "enterprise_active": true}
      ],

      "at_a_glance": {
          "total_successful_jobs": 2700000,
          "active_organizations": 87,
          "featured_template": {"id": 42, "name": "Deploy backend", "count": 98000}
      },

      "user_leaderboard_top10": [
          {"rank": 1, "id": 7, "username": "user_0007", "organization_ids": [3, 1], "count": 4200},
          {"rank": 2, "id": 1423, "username": "user_1423", "organization_ids": [9], "count": 4180},
          {"rank": 3, "id": 891, "username": "user_0891", "organization_ids": [1], "count": 4150},
          {"rank": 10, "id": 332, "username": "user_0332", "organization_ids": [14], "count": 3900}
      ],

      "org_leaderboard_top10": [
          {"rank": 1, "id": 3, "name": "Security", "count": 410000},
          {"rank": 2, "id": 1, "name": "Engineering", "count": 395000},
          {"rank": 3, "id": 9, "name": "DevOps", "count": 380000},
          {"rank": 10, "id": 14, "name": "Sales Ops", "count": 210000}
      ],

      "dimension_top10": {
          "volume": [
              {"rank": 1, "id": 7, "username": "user_0007", "organization_ids": [3, 1], "score": 4200}
          ],
          "breadth": [
              {"rank": 1, "id": 55, "username": "user_0055", "organization_ids": [9], "score": 187}
          ],
          "consistency": [
              {"rank": 1, "id": 1890, "username": "user_1890", "organization_ids": [1], "score": 30}
          ]
      }
  }
  ```

  #### Part 2: Org data (key: `gamification_org_{org_id}`, example for org "Security", id=3)

  ```json
  {
      "organization_id": 3,
      "name": "Security",
      "streak": {
          "days": 25,
          "milestones": [7, 14]
      },
      "calendar_days": ["2026-07-16", "2026-07-17", "2026-07-18", "2026-08-14"],
      "leaderboard_rank": 1,
      "leaderboard_count": 410000,
      "badges": {
          "sustained": true,
          "rising": false,
          "top_tier": true
      },
      "badge_messages": [
          {"badge": "top_tier", "type": "badge_gained", "timestamp": "2026-08-14T09:00:00Z"},
          {"badge": "rising", "type": "badge_lost", "timestamp": "2026-08-12T09:00:00Z"}
      ]
  }
  ```

  Organization badge rules (awarded per organization, visible to all members):

  | Badge | Rule |
  |-------|------|
  | Sustained | 14 or more consecutive org streak days within the 30-day window |
  | Rising | More successful jobs in days 16–30 than in days 1–15 of the window |
  | Top Tier | Org currently ranked #1, #2, or #3 on the org leaderboard (current snapshot only, no historical tracking) |

  #### Part 3: User data (key: `gamification_user_{user_id}`, example for user "user_0007", id=7)

  ```json
  {
      "launched_by_id": 7,
      "username": "user_0007",
      "organization_ids": [3, 1],
      "dimensions": {
          "volume": {"score": 4200, "rank": 1},
          "breadth": {"score": 34, "rank": 82},
          "consistency": {"score": 27, "rank": 15}
      },
      "leaderboard_rank": 1,
      "leaderboard_count": 4200,
      "badges": {
          "ignition": true,
          "week_warrior": true,
          "month_warrior": false,
          "explorer": true,
          "centurion": true,
          "reliable": true,
          "accelerator": true
      },
      "badge_messages": [
          {"badge": "centurion", "type": "badge_gained", "timestamp": "2026-08-14T09:00:00Z"},
          {"badge": "month_warrior", "type": "badge_lost", "timestamp": "2026-08-13T09:00:00Z"}
      ]
  }
  ```

  #### Badge notification messages

  Badges are transient — they are tied to the sliding 30-day window and can appear and
  disappear as the window moves. The `badge_messages` list tracks recent badge transitions
  so the UI can show celebrations (gained) and visual cues (lost).

  **Rules:**

  1. Each message records a single badge transition: `{"badge": "<name>", "type": "badge_gained" | "badge_lost", "timestamp": "<ISO>"}`.

  2. **Only the last transition per badge is stored.** If a badge is gained and a
     `badge_gained` message already exists for it (with no intervening `badge_lost`),
     the existing message's timestamp is replaced. Same vice versa. This means the
     messages list contains at most one entry per badge — always the most recent state change.

  3. **Messages are retained for 3 days max.** During hourly computation, messages
     older than 3 days are pruned before any new messages are appended.

  4. **Messages are cleared on read.** When the user calls the GET API endpoint and
     receives their badge messages, the messages are removed from the stored data
     (the user has "read" them). The next hourly computation starts with an empty
     messages list for that user unless new transitions occur.

  **Computation flow (during hourly task):**

  1. Load previous KV row for the user (contains `badges` map and `badge_messages` list)
  2. Prune messages older than 3 days from the loaded `badge_messages`
  3. Compute new badge states
  4. For each badge that changed vs. previous `badges` map:
     - If badge went `false → true`: check if there's already a `badge_gained` message
       for this badge. If yes, update its timestamp. If no (there's a `badge_lost` or
       nothing), replace/add a `badge_gained` message.
     - If badge went `true → false`: check if there's already a `badge_lost` message
       for this badge. If yes, update its timestamp. If no, replace/add a `badge_lost`
       message.
  5. Save the new row with updated `badges` and `badge_messages`

  The same logic applies to organization badge messages (stored in
  `gamification_org_{org_id}`).

## API

  Endpoint: `GET /api/v1/dashboard_reports/gamification/`

  Response varies by authenticated user. The backend resolves the user's identity
  from the auth token and returns a merged JSON containing exactly:

  1. **Global data** — leaderboard top 10s, enterprise streak, calendar grid, at-a-glance
     (same for all users, from key `gamification_global`)
  2. **Org data** — all orgs the requesting user belongs to
     (from keys `gamification_org_{org_id}` for each org in the user's `organization_ids`)
  3. **One user's data** — the requesting user's dimensions, badges, rank
     (from key `gamification_user_{user_id}`)

### Name anonymization

  The API **anonymizes user names** from organizations that the requesting user does not
  belong to. Specifically:

  - Users who share **at least one common organization** with the requesting user are shown
    with their **full username**.
  - Users who share **no organization** with the requesting user are shown with only the
    **uppercase first letter of each word part**, split by word separators (`_`, `.`, `-`,
    spaces). Examples: `"alice"` → `"A"`, `"bob_smith"` → `"B S"`, `"john.doe"` → `"J D"`.
  - **Organization names** are always shown in full — no anonymization applies to org names.

  This anonymization is applied at API response time. The stored precomputed data retains
  full usernames; the API serializer masks them based on the requesting user's `organization_ids`.

  This applies to all user-referencing fields in the response: `user_leaderboard_top10`,
  `dimension_top10` lists, and any user entries outside the requesting user's own orgs.

### Badge messages — clear on read

  The GET endpoint has a **write side effect**: after returning the response, it clears
  `badge_messages` from the user's KV row and from all of the user's org KV rows. This
  marks the messages as "read." Subsequent GET requests will return an empty
  `badge_messages` list until the next hourly computation produces new transitions.

  Implementation: the clear can be performed asynchronously after the response is sent
  (fire-and-forget update) to avoid adding latency to the read path.

  No path parameters needed — the endpoint always returns data for "me" and "my orgs".
  Under the hood it does 2 + N PK lookups on the key/value table (1 global + 1 user + N orgs)
  and merges the results.

  Response structure:

  ```json
  {
    "computed_at": "2026-08-14T09:00:00Z",
    "global": { ... },
    "my_orgs": [ { ... }, { ... } ],
    "my_user": { ... }
  }
  ```

  Response size: ~30 KB total. Sub-millisecond DB reads from buffer cache.

  If no data are computed yet, the API will return HTTP 200 with an empty payload:

  ```json
  {
    "detail": "Gamification data has not been computed yet. Data will be available after the next hourly computation.",
  }
  ```

## Setting

  The gamification feature is controlled by a runtime setting (`GAMIFICATION` in the
  `dynamic_settings.Setting` model). An administrator can toggle it at runtime without
  restart or redeployment. Default: disabled.

  If the setting is enabled, the API responds with data. If disabled, the API returns HTTP 404:

  ```json
  {
    "detail": "Gamification is not enabled. An administrator can enable it via the GAMIFICATION setting."
  }
  ```

