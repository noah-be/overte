# Pinned upstream regression inputs

Unmodified Qt v6.11.1 sources, retaining upstream copyright and license headers:
- https://github.com/qt/qtbase/blob/v6.11.1/src/corelib/tools/qfreelist_p.h
- https://github.com/qt/qtbase/blob/v6.11.1/src/corelib/thread/qmutex.cpp

The host regression executes the actual free-list and extracted mutex pool
methods. It inserts a scheduling hook before the free-list CAS; it does not
replace that algorithm. The rest of native QMutex is not simulated as qualified.

SHA-256:
- `qfreelist_p.h`: `c2e50875f4dec48992149564bad20ff31a69ec8aefc7bbca2366ed26a55d869b`
- `qmutex.cpp`: `f617eea7f2ebc22540dafdf7734215a8fbca1dce1c3a105b5856bc4b7caff7c9`
