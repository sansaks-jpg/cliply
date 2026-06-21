import { describe, it, expect } from "vitest";
import { cn } from "../utils";

describe("cn utility", () => {
  it("should merge simple class strings", () => {
    expect(cn("class1", "class2")).toBe("class1 class2");
  });

  it("should handle conditional classes", () => {
    expect(cn("class1", true && "class2", false && "class3", null, undefined)).toBe("class1 class2");
  });

  it("should handle objects for conditional classes", () => {
    expect(cn("class1", { class2: true, class3: false })).toBe("class1 class2");
  });

  it("should override conflicting tailwind classes correctly", () => {
    expect(cn("px-2 py-1 bg-red-500", "px-4 bg-blue-500")).toBe("py-1 px-4 bg-blue-500");
  });

  it("should handle arrays of classes", () => {
    expect(cn(["class1", "class2"], ["class3"])).toBe("class1 class2 class3");
  });

  it("should merge complex combinations", () => {
    expect(
      cn(
        "base-class",
        ["array-class-1", "array-class-2"],
        { "conditional-class": true, "ignored-class": false },
        "px-2 bg-red-500",
        "p-4" // p-4 overrides px-2 and py-whatever
      )
    ).toBe("base-class array-class-1 array-class-2 conditional-class bg-red-500 p-4");
  });
});
