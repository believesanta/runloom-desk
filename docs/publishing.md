# Put this project on GitHub

The source archive contains the repository files, including `.github` and `.gitignore`. The Windows archive is a separate downloadable application.

1. Extract `runloom-desk-0.1.2-source.zip` and open the `runloom-desk` folder in your editor.
2. Run the instructions in README and inspect the three examples. Review `docs/architecture.md` so you can explain process ownership, storage and scheduling choices.
3. Create an empty GitHub repository named, for example, `runloom-desk`. Leave automatic README, license and gitignore creation disabled because these files are already included.
4. From the extracted source folder, initialize Git and commit the actual files with your configured author identity:

```powershell
git init -b main
git add .
git status
git commit -m "Add Runloom Desk local automation workbench"
```

5. Follow GitHub's displayed instructions to set your own repository remote and push `main`. Review the remote URL before running the push command.
6. When ready, create a release and attach the separate Windows ZIP. Preserve its complete folder layout, notices and runtime files. Do not add the Windows runtime, personal workspace database or build caches to the source repository.

Suggested repository description: **A local Windows workbench that turns trusted scripts into parameter forms, observable runs and scheduled automations.**

Suggested topics: `windows`, `desktop`, `automation`, `python`, `tkinter`, `sqlite`, `script-runner`.

Keep the documented limitations visible. The included CI workflow will only acquire real run results after you push it to GitHub. This distribution has not been published on your behalf.
