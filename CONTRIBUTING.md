# How to Contribute

This project is [Apache-2.0 licensed] and accepts contributions through
GitHub pull requests.

[Apache-2.0 licensed]:
https://github.com/ansible/metrics-service/blob/devel/LICENSE

## Certificate of Origin

By contributing to this project you agree to the Developer Certificate of
Origin (DCO). This document was created by the Linux Kernel community and is a
simple statement that you, as a contributor, have the legal right to make the
contribution. See the [DCO] file for details.

[DCO]: https://github.com/ansible/metrics-service/blob/devel/DCO

## Principles

This repository adheres to the following principles:

- Open: Contribution is always welcome.
- Respectful: See the [Code of Conduct].
- Transparent and accessible: Work and collaboration should be done in public.
  See [Governance](#governance) section for details.
- Merit: Ideas and contributions are accepted according to their merit and
  alignment with the project objectives principles.

[Code of Conduct]:
https://github.com/ansible/metrics-service/blob/devel/CODE-OF-CONDUCT.md

## How to contribute

We are very happy to receive contributions from the community in any form!

Please use a GitHub pull request to submit your contributions. If you have a
question or are unsure if a contribution is wanted, please join us in
<!--TBD-->#channel-name-here on Matrix to discuss your change or on the Ansible
forum using the TBD tag if you prefer asynchronous discussion.
Open a GitHub issue to report bugs or request features.

## Trace Propagation

New async or outbound HTTP code MUST follow the
[trace propagation standard](docs/trace-propagation-standard.md): request IDs
(`X-Request-ID`) are propagated across async task boundaries and outbound
calls, and all log records carry a `request_id` field. Use its
[conformance checklist](docs/trace-propagation-standard.md#conformance-checklist)
when reviewing changes that add task submission or HTTP client code; record
the filled-in result in the PR description or the Jira ticket.

The standard is being adopted incrementally. Rules the current implementation
does not yet meet are listed in
[Known gaps](docs/trace-propagation-standard.md#known-gaps); they are tracked
follow-ups, not exemptions for new code.

## Governance

The Metrics Service project uses the following governance model:

---
- A patch SHOULD have a minimum of 2 reviews from Members before it is merged.
- Members SHOULD NOT review/merge their own patches except in exceptional
  cases.
---
- All Contributions MUST be done using the GitHub PR process.
- Any Contributor MAY submit any patches they feel are suitable for inclusion.
- Any Contributor MAY review the patches of other Contributors.
- Any Contributor who makes correct patches, writes good reviews, who clearly
  understands the project goals, and the process SHOULD be invited to become a
  Member of the WWG.
---

(inspired by the [C4 process](https://rfc.zeromq.org/spec/42))
