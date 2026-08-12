import { buildPhase, checkGenerated, PromptBundleError, writeAll } from "./prompt-bundler"

function usage(): never {
  console.error("Usage: bun run tools/build-prompts.ts [--check|--phase <phase>]")
  process.exit(2)
}

if (import.meta.main) {
  const root = process.cwd()
  const args = process.argv.slice(2)
  try {
    if (args.includes("--check")) {
      const errors = checkGenerated(root)
      if (errors.length > 0) {
        for (const error of errors) console.error(`✗ ${error}`)
        process.exit(1)
      }
      console.log("✓ Generated prompt bundles are up to date")
    } else if (args[0] === "--phase") {
      const phase = args[1]
      if (!phase || args.length !== 2) usage()
      const result = buildPhase(root, phase)
      const target = `${root}/${result.path}`
      const { mkdirSync, writeFileSync } = await import("node:fs")
      const { dirname } = await import("node:path")
      mkdirSync(dirname(target), { recursive: true })
      writeFileSync(target, result.content, "utf8")
      console.log(`✓ Generated ${result.path}`)
    } else if (args.length === 0) {
      const manifest = writeAll(root)
      console.log("✓ Generated prompts/generated/tony-orchestrator.md")
      console.log(`✓ Generated ${Object.keys(manifest.phases).length} phase bundles`)
      console.log("✓ Generated prompts/generated/prompt-manifest.json")
    } else {
      usage()
    }
  } catch (error) {
    const message = error instanceof PromptBundleError || error instanceof Error ? error.message : String(error)
    console.error(`✗ ${message}`)
    process.exit(1)
  }
}
