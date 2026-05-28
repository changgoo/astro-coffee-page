---
name: Discussed paper
about: Record that a paper was discussed in coffee so the nightly sync can add it to discussed.json
title: "Discussed paper: "
labels: discussed-paper
---

Use this template for papers that were actually discussed in coffee.

Keep the title prefix exactly as `Discussed paper: ` so the nightly workflow can find it.

Fill the body with these machine-readable fields only:

```text
paper_id: 2605.12345
title: Paper title here
arxiv_url: https://arxiv.org/abs/2605.12345
authors: First Author; Second Author; Third Author
```

Notes:
- `authors` should use `;` between names.
- `paper_id`, `title`, and `arxiv_url` should match the paper shown on the site.
- The nightly workflow uses the issue creation timestamp as `discussed_at` and closes the issue after syncing.
