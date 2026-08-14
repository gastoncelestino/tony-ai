import { readFileSync, readdirSync, existsSync, statSync } from "node:fs"
import { resolve } from "node:path"

const ROOT = resolve(process.cwd())
const OPENCODE_JSON = resolve(ROOT, "opencode.json")
const PROMPTS_DIR = resolve(ROOT, "prompts/sdd")
const SHARED_DIR = resolve(ROOT, "skills/_shared")

let errors = 0
let warnings = 0

function fail(message: string): void { console.error(`\x1b[31m✗\x1b[0m ${message}`); errors++ }
function ok(message: string): void { console.log(`\x1b[32m✓\x1b[0m ${message}`) }
function warn(message: string): void { console.warn(`\x1b[33m⚠\x1b[0m ${message}`); warnings++ }
function loadJson(): Record<string, unknown> | null { try { return JSON.parse(readFileSync(OPENCODE_JSON, "utf-8")) } catch { return null } }
function exists(path: string): boolean { return existsSync(resolve(ROOT, path)) }

function checkJsonSyntax(): void { try { JSON.parse(readFileSync(OPENCODE_JSON, "utf-8")); ok("opencode.json: JSON syntax valid") } catch (error) { fail(`opencode.json: JSON syntax error — ${error}`) } }
function checkSkillsDirectory(): void { exists("skills") ? ok("skills/ directory exists") : fail("skills/ directory not found"); exists("skills/_shared") ? ok("skills/_shared/ directory exists") : fail("skills/_shared/ directory not found") }
function checkPromptsDirectory(): void { if (!exists("prompts/sdd")) { fail("prompts/sdd/ directory not found"); return }; ok("prompts/sdd/ directory exists"); const files = readdirSync(PROMPTS_DIR).filter((f) => f.endsWith(".md") && !f.endsWith("SKILL.md")); files.length ? ok(`Found ${files.length} prompt files in prompts/sdd/`) : warn("No .md files found in prompts/sdd/") }
function checkScripts(): void { for (const script of ["scripts/setup.sh", "scripts/health.sh"]) { const path = resolve(ROOT, script); if (!existsSync(path)) fail(`${script} not found`); else if ((statSync(path).mode & 0o111) === 0) warn(`${script} exists but is not executable`); else ok(`${script} exists and executable`) } }
function checkDefaultAgent(): void { const config = loadJson(); if (!config) return; const agent = config.default_agent as string | undefined; if (!agent) return warn("No default_agent defined in opencode.json"); const agents = Object.keys((config.agent ?? {}) as Record<string, unknown>); agents.includes(agent) ? ok(`default_agent "${agent}" exists in agents`) : fail(`default_agent "${agent}" not found in agents`) }
function checkPermissions(): void { const config = loadJson(); if (!config) return; if (!config.permission) return warn("No permission block defined in opencode.json"); ok("permission block exists in opencode.json") }
function checkMcpServers(): void { const config = loadJson(); if (!config) return; if (!config.mcp) return warn("No MCP block defined in opencode.json"); ok("MCP block exists in opencode.json"); for (const [name, cfg] of Object.entries(config.mcp as Record<string, Record<string, unknown>>)) if (!cfg.command && !cfg.url) fail(`MCP server "${name}" missing command or url`) }
function extractFileReferences(text: string): string[] { return [...text.matchAll(/\{file:([^}]+)\}/g)].map((m) => m[1]) }
function extractSharedReferences(text: string): string[] { return [...text.matchAll(/(?:skills\/_shared|\.\.\/_shared)\/[^\s)`'\"]+/g)].map((m) => m[0]) }
function extractAgentReferences(text: string): string[] { return [...text.matchAll(/agent\.([a-z][a-z0-9_-]*[a-z0-9])(?![a-z0-9_.-])/g)].map((m) => m[1]) }
function checkFileReferences(): void { const config = loadJson(); if (!config) return; const refs = new Set<string>(); for (const cfg of Object.values((config.agent ?? {}) as Record<string, {prompt?: string}>)) if (typeof cfg.prompt === "string") for (const ref of extractFileReferences(cfg.prompt)) refs.add(ref); for (const ref of refs) exists(ref) ? ok(`{file:${ref}} exists`) : fail(`{file:${ref}} not found`) }
function checkPromptSourceTokens(): void { const root = resolve(ROOT, "prompts/agents"); if (!existsSync(root)) return fail("prompts/agents/ directory not found"); const pending: string[] = []; const visit = (dir: string): void => { for (const entry of readdirSync(dir, {withFileTypes:true})) { const path = resolve(dir, entry.name); if (entry.isDirectory()) visit(path); else if (entry.isFile() && entry.name.endsWith(".md") && /\{file:[^}]+\}/.test(readFileSync(path,"utf-8"))) pending.push(path) } }; visit(root); pending.length ? pending.forEach((p) => fail(`${p}: native {file:...} token remains in source prompt; use plain documentation`)) : ok("Prompt sources contain no native nested {file:...} references") }
function checkSharedReferences(): void { if (!exists("prompts/sdd")) return fail("prompts/sdd/ directory not found"); const refs = new Set<string>(); for (const name of readdirSync(PROMPTS_DIR).filter((f) => f.endsWith(".md"))) for (const ref of extractSharedReferences(readFileSync(resolve(PROMPTS_DIR,name),"utf-8"))) refs.add(ref); for (const ref of refs) exists(ref) ? ok(`${ref} exists`) : fail(`${ref} not found`) }
function checkAgentReferences(): void { const config = loadJson(); if (!config) return; const agents = new Set(Object.keys((config.agent ?? {}) as Record<string,unknown>)); const refs = new Set<string>(); for (const cfg of Object.values((config.agent ?? {}) as Record<string,{prompt?:string}>)) if (typeof cfg.prompt === "string") for (const ref of extractAgentReferences(cfg.prompt)) refs.add(ref); for (const ref of refs) { if (ref === "md") continue; if ([...agents].some((a) => a !== ref && a.startsWith(ref + "-"))) continue; agents.has(ref) ? ok(`agent.${ref} exists in opencode.json`) : fail(`agent.${ref} referenced in prompt but not found in opencode.json`) } }

function main(): void {
  console.log("\n=== Tony-AI Configuration Validator ===\n")
  checkJsonSyntax(); checkSkillsDirectory(); checkPromptsDirectory(); checkScripts(); checkDefaultAgent(); checkPermissions(); checkMcpServers(); checkFileReferences(); checkSharedReferences(); checkAgentReferences()
  console.log("\n=== Summary ===")
  if (errors === 0) { console.log(warnings === 0 ? "\x1b[32m✓\x1b[0m All checks passed!" : `\x1b[32m✓\x1b[0m All checks passed (${warnings} warning(s))`); process.exit(0) }
  console.log(`\x1b[31m✗\x1b[0m ${errors} error(s) found`); if (warnings) console.log(`\x1b[33m⚠\x1b[0m ${warnings} warning(s) found`); process.exit(1)
}
main()