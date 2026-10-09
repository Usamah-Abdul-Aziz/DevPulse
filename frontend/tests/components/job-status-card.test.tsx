import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { JobStatusCard } from "@/components/repositories/job-status-card";
import * as apiModule from "@/lib/api";
import type { JobResponse } from "@/types";

/**
 * Polling behaviour is the part worth testing: the card must keep polling a `paused` job
 * (rate-limited jobs resume on their own) and stop on `succeeded` or `failed`.
 *
 * The interval is passed as zero so each poll resolves as soon as its promise does. Real timers,
 * not fake ones — React Testing Library's `findByText` polls on `setTimeout` and fake timers
 * freeze that along with the code under test.
 */
describe("JobStatusCard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockJobSequence(...responses: JobResponse[]) {
    const queue = [...responses];
    return vi.spyOn(apiModule.api, "getJob").mockImplementation(async () => {
      const response = queue.shift();
      if (response === undefined) {
        throw new Error("getJob was polled more often than the test expected");
      }
      return response;
    });
  }

  it("renders nothing until a job is selected", () => {
    const { container } = render(<JobStatusCard jobId={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the running state and then stops on success", async () => {
    const getJob = mockJobSequence(
      { id: 1, repository_id: 1, status: "running", counts: { prs: 12, commits: 88 } },
      { id: 1, repository_id: 1, status: "succeeded", counts: { prs: 12, commits: 88 } },
    );
    render(<JobStatusCard jobId={1} intervalMs={0} />);

    expect(await screen.findByText("Ingesting")).toBeVisible();
    expect(screen.getByText("12")).toBeVisible();
    expect(screen.getByText("88")).toBeVisible();

    expect(await screen.findByText("Completed")).toBeVisible();
    expect(getJob).toHaveBeenCalledTimes(2);
  });

  it("keeps polling a paused job instead of treating it as a failure", async () => {
    const paused: JobResponse = {
      id: 1,
      repository_id: 1,
      status: "paused",
      cursor: { phase: "pull_requests" },
    };
    // A paused job keeps answering `paused` until the rate-limit window reopens. The test holds
    // it there so the paused copy is stable on screen instead of being replaced by the next poll
    // before the assertions below can read it.
    const afterPause: JobResponse[] = [
      { id: 1, repository_id: 1, status: "running" },
      { id: 1, repository_id: 1, status: "succeeded" },
    ];
    let windowReopened = false;
    const remaining = [...afterPause];
    vi.spyOn(apiModule.api, "getJob").mockImplementation(async () => {
      if (!windowReopened) return paused;
      const response = remaining.shift();
      if (response === undefined) {
        throw new Error("getJob was polled more often than the test expected");
      }
      return response;
    });

    render(<JobStatusCard jobId={1} intervalMs={0} />);

    expect(await screen.findByText("Paused — rate limited")).toBeVisible();
    // The paused copy explains *why*, so it reads as a deliberate stop rather than a break.
    expect(screen.getByText(/resumes from where it stopped/)).toBeVisible();
    expect(screen.getByText(/pull_requests/)).toBeVisible();

    windowReopened = true;

    expect(await screen.findByText("Ingesting")).toBeVisible();
    expect(await screen.findByText("Completed")).toBeVisible();
  });

  it("shows the backend's error message on failure", async () => {
    mockJobSequence({
      id: 1,
      repository_id: 1,
      status: "failed",
      error: "GitHub returned 404 for acme/widgets",
    });
    render(<JobStatusCard jobId={1} intervalMs={0} />);

    expect(await screen.findByText("Failed")).toBeVisible();
    expect(screen.getByText("GitHub returned 404 for acme/widgets")).toBeVisible();
  });

  it("does not render the counts grid when the job has none yet", async () => {
    mockJobSequence({ id: 1, repository_id: 1, status: "running" });
    render(<JobStatusCard jobId={1} intervalMs={0} />);

    expect(await screen.findByText("Ingesting")).toBeVisible();
    expect(screen.queryByText("PRs")).toBeNull();
  });

  it("reports a polling error without losing the job it already has", async () => {
    mockJobSequence(
      { id: 1, repository_id: 1, status: "running", counts: { prs: 3 } },
      { id: 1, repository_id: 1, status: "succeeded", counts: { prs: 3 } },
    );
    render(<JobStatusCard jobId={1} intervalMs={0} />);

    expect(await screen.findByText("Completed")).toBeVisible();
    expect(screen.getByText("3")).toBeVisible();
    expect(screen.queryByText(/Polling error/)).toBeNull();
  });
});
