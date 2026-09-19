import { describe, expect, it } from "vitest";
import { placeholdersIn, renderTemplate, templateProblems } from "@/lib/templates";

const ALLOWED = ["patient_first_name", "hospital_name", "post_op_day", "checkin_link"];

describe("templateProblems", () => {
  it("accepts wording that only uses known placeholders", () => {
    expect(templateProblems("Hello {patient_first_name}, day {post_op_day}: {checkin_link}", ALLOWED)).toEqual([]);
  });

  it("catches a misspelt placeholder before a patient sees it literally", () => {
    expect(templateProblems("Hello {patient_frist_name}", ALLOWED)).toEqual(["Unknown placeholder: {patient_frist_name}."]);
  });

  it("catches unbalanced braces, empty and over-long messages", () => {
    expect(templateProblems("Hello {patient_first_name", ALLOWED)).toContain("A { or } is missing its partner.");
    expect(templateProblems("   ", ALLOWED)).toContain("The message is empty.");
    expect(templateProblems("x".repeat(1025), ALLOWED)[0]).toMatch(/1024 characters/);
  });
});

describe("renderTemplate", () => {
  it("fills known placeholders and leaves unknown ones visible", () => {
    expect(renderTemplate("Hi {patient_first_name} from {hospital_name} {oops}", { patient_first_name: "Lakshmi", hospital_name: "St. Mary's" }))
      .toBe("Hi Lakshmi from St. Mary's {oops}");
  });

  it("lists placeholders in order", () => {
    expect(placeholdersIn("{a} and {b} and {a}")).toEqual(["a", "b", "a"]);
  });
});
