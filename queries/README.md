# queries/

Named, multi-line SQL statements for `segaudit sql -f queries/<name>.sql`.
Each file is documented at the top: what question it answers and which tables
it needs. They run read-only over the run's tables (see
`docs/04-phase-tutorials/phase-01-data.md`, walk 5).

| File | Question | Tables |
|---|---|---|
| `cases_overview.sql` | What did the inventory find — per source, how many cases, labels, QA failures, and the spacing range? | `cases` |
| `qa_failures.sql` | Which cases failed which input-QA check, and why? | `qa_issues`, `cases` |
| `volumes_by_case.sql` | Hippocampal volumes (ml) per case, anterior and posterior, largest first | `cases` |
| `runs_recent.sql` | The last ten commands that wrote tables, with config, seed and version | `runs` |
