import { describe, expect, it } from "vitest";
import { githubAuthButtonState, parseGitHubAuthStatus } from "./githubAuth";

describe("GitHub auth status parsing", () => {
  it("extracts the logged-in GitHub account from gh output", () => {
    const status = parseGitHubAuthStatus(
      "github.com\n  ✓ Logged in to github.com account shin (/Users/shin/.config/gh/hosts.yml)\n",
      "",
      0
    );

    expect(status.installed).toBe(true);
    expect(status.authenticated).toBe(true);
    expect(status.account).toBe("shin");
  });

  it("reports unauthenticated gh status without storing tokens", () => {
    const status = parseGitHubAuthStatus("", "You are not logged into any GitHub hosts", 1);

    expect(status.installed).toBe(true);
    expect(status.authenticated).toBe(false);
    expect(status.message).toContain("not logged");
  });
});

describe("GitHub auth Sign in / Sign out toggle", () => {
  it("shows Sign out (logout) when authenticated", () => {
    const state = githubAuthButtonState({
      installed: true,
      authenticated: true,
      account: "shin",
      message: "Logged in as shin",
    });

    expect(state.label).toBe("Sign out");
    expect(state.intent).toBe("logout");
    expect(state.warning).toBe(true);
    expect(state.cta).toBe(false);
  });

  it("shows Sign in (login) when not authenticated", () => {
    const state = githubAuthButtonState({
      installed: true,
      authenticated: false,
      message: "not logged in",
    });

    expect(state.label).toBe("Sign in");
    expect(state.intent).toBe("login");
    expect(state.cta).toBe(true);
    expect(state.warning).toBe(false);
  });

  it("shows Sign in when gh is not installed (login flow guides install)", () => {
    const state = githubAuthButtonState({
      installed: false,
      authenticated: false,
      message: "GitHub CLI (gh) is not installed",
    });

    expect(state.label).toBe("Sign in");
    expect(state.intent).toBe("login");
  });
});
