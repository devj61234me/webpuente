import { beforeEach, describe, expect, it, vi } from "vitest";
import axios from "axios";
import { api, errorInfo, fieldErrors, refreshAccess, tokens } from "../api/client";

describe("error helpers", () => {
  it("reads the backend error format", () => {
    const err = { response: { status: 400, data: { error: { code: "weak_password", message: "Too short.", details: { new_password: ["Too short.", "Too common."] } } } } };
    expect(errorInfo(err)).toMatchObject({ status: 400, code: "weak_password", message: "Too short." });
    expect(fieldErrors(err)).toEqual({ new_password: "Too short. Too common." });
  });
  it("explains throttling, server errors and network failures in plain words", () => {
    expect(errorInfo({ response: { status: 429, data: {} } }).message).toMatch(/too many requests/i);
    expect(errorInfo({ response: { status: 502, data: "<html>" } }).message).toMatch(/server had a problem/i);
    expect(errorInfo(new Error("Network Error")).message).toMatch(/cannot reach the server/i);
    expect(errorInfo({ code: "ECONNABORTED" }).code).toBe("timeout");
  });
});

describe("token handling", () => {
  beforeEach(() => { tokens.clear(); vi.restoreAllMocks(); });

  it("keeps the access token in memory and the refresh token in localStorage", () => {
    tokens.set("A1", "R1");
    expect(tokens.access).toBe("A1");
    expect(localStorage.getItem("wp_refresh")).toBe("R1");
    expect(localStorage.getItem("wp_access")).toBeNull();
    tokens.clear();
    expect(tokens.access).toBeNull();
    expect(tokens.refresh).toBeNull();
  });

  it("sends only ONE refresh request when several calls need a new token", async () => {
    tokens.set("old", "R1");
    const post = vi.spyOn(axios, "post").mockResolvedValue({ data: { access: "A2", refresh: "R2" } });
    const results = await Promise.all([refreshAccess(), refreshAccess(), refreshAccess()]);
    expect(results).toEqual(["A2", "A2", "A2"]);
    expect(post).toHaveBeenCalledTimes(1);
    expect(tokens.refresh).toBe("R2"); // rotated token is stored
  });

  it("fails clearly when there is no refresh token", async () => {
    await expect(refreshAccess()).rejects.toThrow();
  });

  it("adds the bearer token to requests", async () => {
    tokens.set("A9", "R9");
    const handler = api.interceptors.request.handlers[0].fulfilled;
    const config = handler({ headers: {} });
    expect(config.headers.Authorization).toBe("Bearer A9");
  });
});
