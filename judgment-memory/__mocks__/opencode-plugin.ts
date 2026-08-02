/**
 * __mocks__/opencode-plugin.ts
 * Mock del OpenCode plugin context para tests.
 * Proporciona funciones factory para crear inputs/outputs mock de cada hook.
 */

export interface MockHookInput {
  sessionID: string
  directory: string
  tool?: string
  [key: string]: any
}

export interface MockHookOutput {
  parts?: Array<{ type: string; text?: string }>
  system?: string[]
  context?: string[]
  [key: string]: any
}

export interface MockPluginContext {
  directory: string
  events: Array<{ type: string; properties?: Record<string, any> }>
  hooks: Record<string, (input: any, output: any) => Promise<void> | void>
}

export function createMockContext(
  directory: string,
  sessionId = "test-session-123"
): MockPluginContext {
  return {
    directory,
    events: [],
    hooks: {}
  }
}

export function createMockChatMessage(content: string, sessionId = "test-session"): Promise<{ input: MockHookInput; output: MockHookOutput }> {
  return Promise.resolve({
    input: { sessionID: sessionId, directory: "/tmp/test" },
    output: {
      parts: [{ type: "text", text: content }],
      message: { summary: { title: content.slice(0, 50), body: "" } }
    }
  })
}

export async function createMockChatMessageEmpty(sessionId = "test-session"): Promise<{ input: MockHookInput; output: MockHookOutput }> {
  return {
    input: { sessionID: sessionId, directory: "/tmp/test" },
    output: {
      parts: [],
      message: { summary: { title: "empty", body: "" } }
    }
  }
}

export function createMockTaskOutput(
  sessionId: string,
  output: string,
  tool = "Task"
): [MockHookInput, MockHookOutput] {
  return [
    { sessionID: sessionId, directory: "/tmp/test", tool },
    { parts: [{ type: "text", text: output }] }
  ]
}

export function createMockSystemTransform(sessionId = "test-session"): [MockHookInput, MockHookOutput] {
  return [
    { sessionID: sessionId, directory: "/tmp/test" },
    { system: ["existing instructions"], context: [] }
  ]
}

export function createMockSessionCreated(sessionId: string, isSubAgent = false): { event: MockEvent } {
  return {
    event: {
      type: "session.created",
      properties: {
        info: {
          id: sessionId,
          parentID: isSubAgent ? "parent-123" : undefined,
          title: isSubAgent ? "Test subagent)" : "Test session"
        }
      }
    }
  }
}

export async function runMockPlugin(
  pluginModule: any,
  ctx: Partial<MockPluginContext> = {}
): Promise<Record<string, (input: any, output: any) => Promise<void> | void>> {
  const context = {
    directory: ctx.directory ?? "/tmp/test",
    events: [],
    ...ctx
  }
  const hooks = await pluginModule.JudgmentMemory(context)
  return hooks
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
