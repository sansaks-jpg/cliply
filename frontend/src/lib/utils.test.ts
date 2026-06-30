import { describe, it, expect } from "vitest";
import { cn } from "./utils";

describe("cn utility", () => {
  it("should merge basic string classes", () => {
    expect(cn("class1", "class2")).toBe("class1 class2");
  });

  it("should handle conditional classes", () => {
    expect(cn("class1", { class2: true, class3: false })).toBe("class1 class2");
  });

  it("should handle arrays of classes", () => {
    expect(cn(["class1", "class2"], "class3")).toBe("class1 class2 class3");
  });

  it("should resolve tailwind class conflicts", () => {
    expect(cn("bg-red-500", "bg-blue-500")).toBe("bg-blue-500");
    expect(cn("p-2", "p-4")).toBe("p-4");
    expect(cn("text-sm", "text-lg")).toBe("text-lg");
  });

  it("should handle falsy values gracefully", () => {
    expect(cn("class1", null, undefined, false, 0, "")).toBe("class1");
  });
});
