import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import createWrapper from "@cloudscape-design/components/test-utils/dom";
import { afterEach, describe, expect, it } from "vitest";
import App, { REPOSITORY } from "./App.jsx";

function check(name, status, extra = {}) {
  return {
    check: name,
    description: `${name} description`,
    status,
    required: true,
    weight: 6,
    loe: 1,
    remediationLink: "https://docs.aws.amazon.com/example",
    ...extra,
  };
}

function reportData(overrides = {}) {
  return {
    checks: [
      check("AWS Organization exists", "complete"),
      check("Service Control Policies enabled", "incomplete"),
      check("Control Tower deployed", "error", { error: "AccessDenied" }),
    ],
    maturity: {
      level: 2,
      name: "Established",
      description: "AWS Organizations in place with OU structure.",
      next_level: 3,
      next_level_progress: 45.5,
      next_level_checks_needed: ["Service Control Policies enabled"],
      scoring_model: {
        rule: "The model assigns the highest maturity level whose required criteria are all complete.",
        weight_note: "Check weights prioritize recommended next steps.",
        levels: [
          {
            level: 1,
            name: "Base",
            description: "Baseline.",
            state: "achieved",
            criteria: [],
            complete_count: 0,
            criteria_count: 0,
          },
          {
            level: 2,
            name: "Established",
            description: "Established.",
            state: "current",
            criteria: [{ name: "AWS Organization exists", status: "complete" }],
            complete_count: 1,
            criteria_count: 1,
          },
          {
            level: 3,
            name: "Intermediate",
            description: "Intermediate.",
            state: "next",
            criteria: [
              { name: "Service Control Policies enabled", status: "incomplete" },
              { name: "Control Tower deployed", status: "error" },
              { name: "Cost and Usage Report configured", status: "not_assessed" },
            ],
            complete_count: 0,
            criteria_count: 3,
          },
        ],
      },
    },
    delegated_admins: [
      { accountId: "222222222222", accountName: "Security", services: ["guardduty.amazonaws.com"] },
    ],
    account_info: {
      account_id: "111111111111",
      account_type: "management",
      is_management_account: true,
    },
    axis_scores: [
      { name: "Multi-Account Environment", score: 50, check_count: 2 },
      { name: "Networking & Connectivity", score: 0, check_count: 0 },
    ],
    summary: { total: 3, complete: 1, incomplete: 1, errors: 1, pct: 33 },
    ...overrides,
  };
}

function renderReport(overrides) {
  const result = render(<App data={reportData(overrides)} />);
  return { ...result, wrapper: createWrapper(result.container) };
}

afterEach(() => {
  cleanup();
  document.body.className = "";
});

describe("report UI", () => {
  it("renders every report section with Cloudscape navigation", () => {
    const { wrapper } = renderReport();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain(
      "Well-Architected Foundations Assessment Report",
    );
    const nav = wrapper.findSideNavigation();
    const hrefs = [
      "#overview",
      "#maturity",
      "#capabilities",
      "#checks",
      "#delegated-admins",
      "#methodology",
    ];
    hrefs.forEach((href) => expect(nav.findLinkByHref(href)).not.toBeNull());
    expect(wrapper.findAppLayout()).not.toBeNull();
    expect(wrapper.findBarChart()).not.toBeNull();
    expect(wrapper.findSteps()).not.toBeNull();
  });

  it("shows maturity level, progress, and next steps", () => {
    const { wrapper } = renderReport();
    expect(screen.getByText("L2")).toBeTruthy();
    expect(wrapper.findProgressBar().getElement().textContent).toContain(
      "Progress toward Level 3",
    );
    const steps = wrapper.findSteps().getElement().textContent;
    expect(steps).toContain("Current level");
    expect(steps).toContain("Next target");
    expect(steps).toContain("1/1 criteria");
    expect(steps).toContain("Baseline");
  });

  it("distinguishes every criterion status in the methodology", () => {
    const { container } = renderReport();
    const methodology = container.querySelector("#methodology");
    const text = methodology.textContent;
    expect(text).toContain("Level 3 — Intermediate");
    expect(text).toContain("Not complete");
    expect(text).toContain("Error");
    expect(text).toContain("Not assessed");
    expect(text).toContain("highest maturity level whose required criteria are all complete");
  });

  it("filters check results by status", () => {
    const { wrapper } = renderReport();
    const table = wrapper.findTable();
    expect(table.findRows()).toHaveLength(3);
    wrapper.findSegmentedControl().findSegmentById("error").click();
    const rows = wrapper.findTable().findRows();
    expect(rows).toHaveLength(1);
    expect(rows[0].getElement().textContent).toContain("Control Tower deployed");
    expect(rows[0].getElement().textContent).toContain("AccessDenied");
  });

  it("filters check results by text", () => {
    const { wrapper } = renderReport();
    wrapper.findTextFilter().findInput().setInputValue("organization");
    expect(wrapper.findTable().findRows()).toHaveLength(1);
  });

  it("renders untrusted text as text", () => {
    const { container } = renderReport({
      checks: [check("<script>alert(1)</script>", "incomplete")],
    });
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });

  it("does not link non-HTTP remediation URLs", () => {
    const { container } = renderReport({
      checks: [check("Bad link", "incomplete", { remediationLink: "javascript:alert(1)" })],
    });
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
  });

  it("caveats limited account maturity", () => {
    const { wrapper } = renderReport({
      account_info: { account_id: "111111111111", account_type: "member", is_management_account: false },
    });
    const alert = wrapper.findAlert().getElement().textContent;
    expect(alert).toContain("Limited assessment");
    expect(alert).toContain("maturity level is provisional for the member account");
  });

  it("omits the delegated administrators section when empty", () => {
    const { container, wrapper } = renderReport({ delegated_admins: [] });
    expect(container.querySelector("#delegated-admins")).toBeNull();
    expect(wrapper.findSideNavigation().findLinkByHref("#delegated-admins")).toBeNull();
  });

  it("reports the uncovered networking axis", () => {
    const { container } = renderReport();
    expect(container.querySelector("#capabilities").textContent).toContain(
      "Networking & Connectivity: no Phase 1 checks",
    );
  });

  it("toggles between light and dark mode from the top navigation", () => {
    const { container } = renderReport();
    // TopNavigation also renders hidden copies of utilities to measure
    // overflow, so select the toggle by its accessible label.
    const toggle = (label) =>
      container.querySelector(`#wafa-top-nav [aria-label="${label}"]`);
    fireEvent.click(toggle("Switch to dark mode"));
    expect(document.body.classList.contains("awsui-dark-mode")).toBe(true);
    fireEvent.click(toggle("Switch to light mode"));
    expect(document.body.classList.contains("awsui-dark-mode")).toBe(false);
  });

  it("lists delegated administrators", () => {
    const { container } = renderReport();
    const section = within(container.querySelector("#delegated-admins"));
    expect(section.getByText("222222222222")).toBeTruthy();
    expect(section.getByText("guardduty.amazonaws.com")).toBeTruthy();
  });

  it("links to the GitHub repository in the footer", () => {
    const { container } = renderReport();
    const footer = container.querySelector("footer");
    expect(footer.textContent).toContain("aws-samples/sample-wa-foundations-assessment");
    const link = footer.querySelector(`a[href="${REPOSITORY.url}"]`);
    expect(link).not.toBeNull();
    expect(REPOSITORY.url).toBe(
      "https://github.com/aws-samples/sample-wa-foundations-assessment",
    );
  });
});
