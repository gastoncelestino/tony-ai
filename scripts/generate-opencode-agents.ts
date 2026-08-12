import { readFileSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"

const ROOT = resolve(process.cwd())
const MANIFEST = resolve(ROOT, "prompts/agents/includes/phase-manifest.json")
const OPENCODE = resolve(ROOT, "opencode.json")

const manifest = JSON.parse(readFileSync(MANIFEST, "utf-8"))
const opencode = JSON.parse(readFileSync(OPENCODE, "utf-8"))

const phases = [
  ...Object.keys(manifest.phases || {}),
  ...Object.keys(manifest.review_phases || {}),
]

const agents: Record<string, { prompt: string }> = {}
for (const phase of phases) {
  agents[phase] = {
    prompt: `{file:./prompts/generated/phases/${phase}.md}`,
  }
}

for (const [name, config] of Object.entries(opencode.agent || {})) {
  if (!agents[name]) {
    agents[name] = config
  }
}

opencode.agent = agents
writeFileSync(OPENCODE, JSON.stringify(opencode, null, 2) + "\n", "utf-8")
console.log(`✓ Generated ${phases.length} phase agents in opencode.json`)
