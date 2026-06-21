import { describe, it, expect } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/setup";
import { getAvailableEncoders, API_URL } from "./api";

describe("api", () => {
  describe("getAvailableEncoders", () => {
    it("returns the available encoders on success", async () => {
      server.use(
        http.get(`${API_URL}/encoders`, () => {
          return HttpResponse.json({ available: ["h264", "hevc"], current: "h264" });
        })
      );

      const result = await getAvailableEncoders();
      expect(result).toEqual({ available: ["h264", "hevc"], current: "h264" });
    });

    it("returns a fallback object on non-ok response", async () => {
      server.use(
        http.get(`${API_URL}/encoders`, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );

      const result = await getAvailableEncoders();
      expect(result).toEqual({ available: ["auto", "cpu"], current: "auto" });
    });
  });
});
