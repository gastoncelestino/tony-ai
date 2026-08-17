import { describe, expect, test } from "bun:test"
import { authorizeToolPaths } from "../plugins/tony-kernel/path-authorization"

describe("Tony Kernel path authorization", () => {
  test("allows when every explicit path is authorized", async () => {
    const result = await authorizeToolPaths(
      ["src/app.ts", "src/lib.ts"],
      async () => ({ allowed: true, reason: "allowed" }),
    )

    expect(result).toEqual({ allowed: true, denied: [] })
  })

  test("returns every denied explicit path", async () => {
    const result = await authorizeToolPaths(
      ["src/app.ts", "secrets/key.pem", "config/dev.ts"],
      async (path) => ({
        allowed: path !== "secrets/key.pem",
        reason: "policy",
      }),
    )

    expect(result).toEqual({
      allowed: false,
      denied: ["secrets/key.pem"],
    })
  })
})
