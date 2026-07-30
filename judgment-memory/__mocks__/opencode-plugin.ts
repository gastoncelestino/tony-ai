import type { Plugin } from "@opencode-ai/plugin"

export interface MockEvent {
  type: string
  properties?: Record<string, any>
}

export interface MockHookInput {
  sessionID: string
  directory: string
  tool?: string
  [key: string]: any
}

export interface MockHookOutput {
  parts?: Array<{ type: string; text?: string }>
  message?: { summary?: { title?: string; body?: string } }
  system?: string[]
  context?: string[]
  [key: string]: any
}

export interface MockPluginContext {
  directory: string
  events: MockEvent[]
  hooks: Record<string, (input: any, output: any) => Promise<void> | void>
}

export function createMockChatMessage(
  sessionID: string,
  content: string,
  directory: string = "/test/project"
): [MockHookInput, MockHookOutput] {
  return [
    { sessionID, directory },
    {
      parts: [{ type: "text", text: content }],
      message: { summary: { title: "", body: "" } }
    }
  ]
}

export function createMockChatMessageEmpty(
  sessionID: string,
  summary: { title: string; body: string },
  directory: string = "/test/project"
): [MockHookInput, MockHookOutput] {
  return [
    { sessionID, directory },
    {
      parts: [],
      message: { summary }
    }
  ]
}

export function createMockTaskOutput(
  sessionID: string,
  output: string,
  directory: string = "/test/project"
): [MockHookInput, MockHookOutput] {
  return [
    { sessionID, directory, tool: "Task" },
    { text: output }
  ]
}

export function createMockTaskOutputObject(
  sessionID: string,
  output: Record<string, any>,
  directory: string = "/test/project"
): [MockHookInput, MockHookOutput] {
  return [
    { sessionID, directory, tool: "Task" },
    { result: output }
  ]
}

export function createMockSystemTransform(
  sessionID: string,
  directory: string = "/test/project"
): [MockHookInput, MockHookOutput] {
  return [
    { sessionID, directory },
    { system: ["existing system prompt"], context: [] }
  ]
}

export function createMockSessionCreated(
  sessionId: string,
  parentID?: string,
  title?: string
): MockEvent {
  return {
    type: "session.created",
    properties: {
      info: {
        id: sessionId,
        parentID,
        title: title ?? "Test Session"
      }
    }
  }
}

export async function runMockPlugin(
  pluginFactory: (ctx: any) => Promise<Record<string, any>>,
  ctx: { directory: string }
): Promise<Record<string, (input: any, output: any) => Promise<void> | void>> {
  const events: MockEvent[] = []

  return await pluginFactory({
    directory: ctx.directory,
    event: async ({ event }: { event: MockEvent }) => {
      events.push(event)
    }
  })
}

export function getHookResult(
  hooks: Record<string, (input: any, output: any) => Promise<void> | void>,
  hookName: string,
  input: MockHookInput,
  output: MockHookOutput
): MockHookOutput {
  const hook = hooks[hookName]
  if (!hook) {
    throw new Error(`Hook "${hookName}" not found`)
  }
  const result = hook(input, output)
  if (result instanceof Promise) {
    throw new Error(`Hook "${hookName}" is async — use await runHook() instead`)
  }
  return output
}

export async function runHook(
  hooks: Record<string, (input: any, output: any) => Promise<void> | void>,
  hookName: string,
  input: MockHookInput,
  output: MockHookOutput
): Promise<MockHookOutput> {
  const hook = hooks[hookName]
  if (!hook) {
    throw new Error(`Hook "${hookName}" not found`)
  }
  await hook(input, output)
  return output
}
