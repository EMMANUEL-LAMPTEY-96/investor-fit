# Templates for your own lists

Fill these in (Excel or Google Sheets, then save as CSV) and attach them in Claude. You can also
just paste a list, a term sheet or a PDF; Claude will convert it.

**funder_list_template.csv**: institutions you want checked. Lists inside a cell are separated by
semicolons. Leave a cell empty if you don't know it. Allowed values are in `../SKILL.md`.

**checklist_template.csv**: any checklist the company should be tested against. Types:

| type | meaning | fill in |
|---|---|---|
| min / max | a number must be at least / at most a value | field, value |
| equals | a fact must equal a value | field, value |
| one_of | a fact must be one of several values | field, value (separated by ;) |
| yes | a fact must be true | field |
| document | the company must hold a document | document |
| judgement | needs an assessment (Claude reasons it out and explains) | requirement |

Delete the example rows before use.
