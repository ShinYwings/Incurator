import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("logger", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("always emits warn and error with the [Incurator] prefix", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const { logger } = await import("./logger");

    logger.warn("w");
    logger.error("e");

    expect(warn).toHaveBeenCalledWith("[Incurator]", "w");
    expect(error).toHaveBeenCalledWith("[Incurator]", "e");
  });

  it("suppresses debug/info when the debug flag is off (default)", async () => {
    const debug = vi.spyOn(console, "debug").mockImplementation(() => {});
    const info = vi.spyOn(console, "info").mockImplementation(() => {});
    const { logger } = await import("./logger");

    logger.debug("d");
    logger.info("i");

    expect(debug).not.toHaveBeenCalled();
    expect(info).not.toHaveBeenCalled();
  });

  it("emits debug/info when localStorage['incurator-debug'] === '1'", async () => {
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => (k === "incurator-debug" ? "1" : null),
    });
    vi.resetModules(); // re-capture DEBUG at module load
    const debug = vi.spyOn(console, "debug").mockImplementation(() => {});
    const { logger } = await import("./logger");

    logger.debug("d");

    expect(debug).toHaveBeenCalledWith("[Incurator]", "d");
  });

  it("does not throw when localStorage is unavailable (graceful default off)", async () => {
    // node/test env has no localStorage; the module-load read must not throw.
    const debug = vi.spyOn(console, "debug").mockImplementation(() => {});
    const { logger } = await import("./logger");
    expect(() => logger.debug("d")).not.toThrow();
    expect(debug).not.toHaveBeenCalled();
  });
});
