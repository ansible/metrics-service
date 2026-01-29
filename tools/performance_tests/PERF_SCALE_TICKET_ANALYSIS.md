# Performance & Scale Ticket Analysis

**Generated:** 2026-01-27
**Purpose:** Understanding and tracking the Perf & Scale ticket requirements

---

## Understanding Your Perf & Scale Ticket

Based on the ticket and existing testing infrastructure, here's what this is asking for:

### **What You Need to Finalize (Before Testing)**

**1. Environment Requirements**
   - Where will this be tested: OpenShift? Containerized? SaaS environment?
   - Current state: You have Docker setup, but need to confirm production-like environment

**2. Data Scale Target**
   - Ticket suggests: **100,000 hosts × 1,000 jobs/hour × 500 tasks each** = massive scale
   - Your current testing: 10M events (Large dataset) = ~416,667 events/hour
   - **Gap**: You need to test at ~50M events/hour (100K hosts × 500 tasks) to meet their target

**3. Monitoring Requirements**
   - Target: **<2% CPU/memory/IO impact** on the platform
   - Current state: You measure memory and duration, but need CPU and IO metrics
   - **Gap**: Need to add CPU and disk I/O monitoring to your test suite

**4. Regression Requirements**
   - Ensure metrics service doesn't impact existing systems:
     - SaaS billing utilities
     - HCC admin dashboard
     - Monthly renewal reports
   - Target: <2% performance degradation after installing metrics service
   - **Gap**: No regression testing framework yet - need before/after comparisons

**5. Testing Duration**
   - Requirement: **Minimum one month of data**
   - Your current testing: 24 hours of data (72 collections)
   - **Gap**: Need to scale to ~30 days and verify no performance degradation over time

---

## Critical Questions You Need to Answer

The ticket lists specific questions that must be answered. Here's the status based on the codebase:

| Question | Current Answer | Status |
|----------|----------------|--------|
| **Retention policy - how long is raw data kept?** | Need to check cleanup tasks | ⚠️ Unclear |
| **Data accumulation per month at scale?** | ~150-200 MB/M events | ✅ Known |
| **Failure/retry strategy for collection?** | Need to document | ⚠️ Exists but undocumented |
| **How is 2-3% impact enforced?** | Not enforced currently | ❌ Missing |
| **Container resource limits?** | Need to define | ❌ Missing |
| **I/O throttling mechanisms?** | Need to define | ❌ Missing |
| **Database connection pooling limits?** | Need to check Django settings | ⚠️ Unclear |
| **Multi-tenant isolation in SaaS?** | Need architecture review | ❌ Missing |
| **Horizontal scaling capability?** | Single-instance currently | ❌ Single only |
| **Work distribution/parallelization?** | Sequential is faster (proven) | ✅ Tested |

---

## What You've Already Accomplished ✅

Your team has done significant work:

- ✅ **Performance testing infrastructure** - Complete scripts in `tools/performance_tests/`
- ✅ **Three dataset sizes tested** - Small (100K), Medium (1M), Large (10M events)
- ✅ **Key finding**: Sequential execution 2.3-3.1x faster than parallel
- ✅ **Memory profiling**: ~160 MB per million events
- ✅ **Scalability validation**: Linear O(n) performance confirmed

---

## What's Missing for This Ticket

**High Priority:**

1. **Scale up testing** - Need to test 50M+ events/hour (100K hosts × 500 tasks)
2. **Add CPU monitoring** - Currently only tracking memory and duration
3. **Add I/O monitoring** - Need disk read/write metrics
4. **Define resource limits** - Container CPU/memory limits, connection pools
5. **30-day test run** - Currently only testing 24 hours of data
6. **Multi-environment testing** - OpenShift, containerized, SaaS

**Medium Priority:**

7. **Regression testing framework** - Before/after comparisons
8. **Document failure/retry strategy**
9. **Document retention policies**
10. **Multi-tenant isolation design** (if applicable)

---

## For Your Meeting - Key Talking Points

**What to say:**

1. "We have comprehensive performance testing infrastructure in place covering small, medium, and large datasets"
2. "Current testing shows sequential execution is optimal (2.3-3x faster than parallel)"
3. "We've validated up to 10M events with predictable memory usage"
4. "We need to scale testing to match the 100K host × 500 task target (~50M events/hour)"
5. "We need to add CPU and I/O monitoring to our test suite"
6. "We need to run tests for 30 days minimum, not just 24 hours"
7. "We need to define and enforce resource limits (containers, DB connections)"

**Questions to ask:**

1. "Is the 100K hosts × 1,000 jobs × 500 tasks the actual production target or worst-case scenario?"
2. "Which environments are priority: OpenShift, containerized Docker, or SaaS?"
3. "Do we need multi-tenant testing or is this single-tenant?"
4. "What systems should we include in regression testing?"

---

## Ticket Requirements Breakdown

### User Story
**As a Platform Administrator I want the metrics service to have undergone appropriate perf and scale testing so that my production jobs are not impacted by this new service**

### Definition of Done
- Metrics service meets perf and scale expectations
- Service is appropriately tested by perf and scale to ensure production jobs will not be impacted
- All perf and scale questions are answered (see table above)
- All defined environments are spun up and tested over the defined timeline, meeting the defined benchmarks

### Requirements Summary

**Environment Finalization:**
- Containerized setup
- OpenShift deployment
- SaaS configuration

**Data Scale Finalization:**
- 100,000 hosts
- 1,000 jobs per hour
- 500 tasks per job

**Monitoring Requirements:**
- <2% CPU impact on platform
- <2% memory impact on platform
- <2% IO impact on platform

**Regression Requirements:**
- Metrics utility powering SaaS billing
- HCC admin dashboard
- Monthly renewal reports
- <2% impact before and after installing metrics service

**Testing Length:**
- Minimum one month of data

**Verification:**
- Metrics service passes all defined tests

---

## Next Steps

### Immediate Actions
1. Schedule discussion with Perf & Scale team to clarify requirements
2. Determine priority environments (OpenShift/Containerized/SaaS)
3. Define resource limits for containers
4. Document retry/failure strategies
5. Document data retention policies

### Short-term Actions (1-2 weeks)
1. Extend test data generation to 30 days
2. Add CPU monitoring to performance tests
3. Add I/O monitoring to performance tests
4. Test at 50M+ events/hour scale
5. Create regression testing framework

### Long-term Actions (2-4 weeks)
1. Run 30-day continuous performance tests
2. Multi-environment deployment testing
3. Regression testing against existing systems
4. Document and enforce resource limits
5. Complete all questions in the requirements table

---

## Resource Estimates

### For 100K Hosts × 1K Jobs/Hour × 500 Tasks

**Projected Scale:**
- Events per hour: 50,000,000 (50M)
- Events per day: 1,200,000,000 (1.2B)
- Events per month: 36,000,000,000 (36B)

**Storage Estimates** (based on current 150-200 MB/M events):
- Daily: ~180-240 GB raw data
- Monthly: ~5.4-7.2 TB raw data

**Memory Estimates** (based on current 160 MB/M events):
- Rollup processing: ~8 GB per processing run

**Performance Estimates** (extrapolated from current tests):
- Individual rollup: ~50-60 seconds
- Sequential execution: ~10-15 ms (with cache warming)

---

## Open Questions for Team Discussion

1. What is the realistic production target vs worst-case scenario?
2. Can we partition/shard data to handle 50M events/hour?
3. Should we implement horizontal scaling or stick with vertical?
4. What is the acceptable latency for metrics collection?
5. Do we need real-time processing or can we batch?
6. What are the actual SLA requirements for the metrics service?
7. Is there a budget for infrastructure scaling?
8. What monitoring tools will be used in production?

---

## References

- [Current Performance Test Results](./PERFORMANCE_TEST_RESULTS.md)
- [Performance Testing Usage Guide](./USAGE.md)
- [Jira Ticket: AAP-56173](https://issues.redhat.com/browse/AAP-56173)