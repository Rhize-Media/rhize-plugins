import { describe, it, expect } from "vitest";
import neo4j from "neo4j-driver";
import { toPlain } from "@/lib/neo4j/queries";

describe("toPlain", () => {
  it("passes through null and undefined", () => {
    expect(toPlain(null)).toBeNull();
    expect(toPlain(undefined)).toBeUndefined();
  });

  it("passes through primitives unchanged", () => {
    expect(toPlain("hello")).toBe("hello");
    expect(toPlain(42)).toBe(42);
    expect(toPlain(true)).toBe(true);
    expect(toPlain(false)).toBe(false);
  });

  it("converts Neo4j Integer to JS number when safe", () => {
    const int = neo4j.int(42);
    expect(toPlain(int)).toBe(42);
  });

  it("converts Neo4j Integer to string when too large for JS number", () => {
    const int = neo4j.int("9007199254740993"); // > Number.MAX_SAFE_INTEGER
    expect(toPlain(int)).toBe("9007199254740993");
  });

  it("converts Neo4j DateTime to ISO string", () => {
    const dt = new neo4j.types.DateTime(2026, 4, 5, 12, 30, 0, 0, 0);
    const result = toPlain(dt);
    expect(typeof result).toBe("string");
    expect(result).toContain("2026");
  });

  it("converts Neo4j Date to string", () => {
    const d = new neo4j.types.Date(2026, 4, 5);
    const result = toPlain(d);
    expect(typeof result).toBe("string");
    expect(result).toContain("2026");
  });

  it("recursively converts arrays", () => {
    const arr = [neo4j.int(1), neo4j.int(2), neo4j.int(3)];
    expect(toPlain(arr)).toEqual([1, 2, 3]);
  });

  it("recursively converts objects", () => {
    const obj = {
      id: "abc",
      count: neo4j.int(10),
      nested: { volume: neo4j.int(500) },
    };
    expect(toPlain(obj)).toEqual({
      id: "abc",
      count: 10,
      nested: { volume: 500 },
    });
  });

  it("handles mixed arrays and objects", () => {
    const input = {
      items: [
        { name: "a", count: neo4j.int(1) },
        { name: "b", count: neo4j.int(2) },
      ],
    };
    expect(toPlain(input)).toEqual({
      items: [
        { name: "a", count: 1 },
        { name: "b", count: 2 },
      ],
    });
  });

  it("handles empty arrays and objects", () => {
    expect(toPlain([])).toEqual([]);
    expect(toPlain({})).toEqual({});
  });
});
