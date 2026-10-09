import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConnectForm } from "@/components/repositories/connect-form";
import * as apiModule from "@/lib/api";

function renderForm() {
  const onConnected = vi.fn();
  render(<ConnectForm onConnected={onConnected} />);
  return onConnected;
}

function mockConnect(response: object) {
  return vi.spyOn(apiModule.api, "connectRepository").mockResolvedValue(response as never);
}

describe("ConnectForm", () => {
  it("submits a normalized repository name", async () => {
    const user = userEvent.setup();
    const onConnected = renderForm();
    const connect = mockConnect({
      job_id: 7,
      repository_id: 3,
      status: "pending",
    });

    await user.type(screen.getByPlaceholderText("fastapi/fastapi"), "  FastAPI/fastapi  ");
    await user.click(screen.getByRole("button", { name: /connect/i }));

    await waitFor(() => {
      expect(connect).toHaveBeenCalledWith("FastAPI/fastapi");
    });
    expect(onConnected).toHaveBeenCalledWith({ job_id: 7, repository_id: 3, status: "pending" });
  });

  it("clears the field after a successful connect", async () => {
    const user = userEvent.setup();
    renderForm();
    mockConnect({ job_id: 1, repository_id: 1, status: "pending" });

    const input = screen.getByPlaceholderText("fastapi/fastapi");
    await user.type(input, "acme/widgets");
    await user.click(screen.getByRole("button", { name: /connect/i }));

    await waitFor(() => {
      expect(input).toHaveValue("");
    });
  });

  it("shows the backend's problem detail when the connect fails", async () => {
    const user = userEvent.setup();
    renderForm();
    vi.spyOn(apiModule.api, "connectRepository").mockRejectedValue(
      new apiModule.ApiError(403, "'evil/corp' is not in the ALLOWED_REPOS list."),
    );

    await user.type(screen.getByPlaceholderText("fastapi/fastapi"), "evil/corp");
    await user.click(screen.getByRole("button", { name: /connect/i }));

    expect(await screen.findByText("'evil/corp' is not in the ALLOWED_REPOS list.")).toBeVisible();
  });

  it("rejects an empty submission without calling the API", async () => {
    const user = userEvent.setup();
    const onConnected = renderForm();
    const connect = mockConnect({ job_id: 1, repository_id: 1, status: "pending" });

    await user.click(screen.getByRole("button", { name: /connect/i }));

    expect(await screen.findByText("Enter a repository as owner/name.")).toBeVisible();
    expect(connect).not.toHaveBeenCalled();
    expect(onConnected).not.toHaveBeenCalled();
  });

  it("disables the submit button while the request is in flight", async () => {
    const user = userEvent.setup();
    renderForm();
    let resolveConnect: (value: object) => void = () => undefined;
    vi.spyOn(apiModule.api, "connectRepository").mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveConnect = resolve;
        }) as never,
    );

    const button = screen.getByRole("button", { name: /connect/i });
    await user.type(screen.getByPlaceholderText("fastapi/fastapi"), "acme/widgets");
    await user.click(button);

    expect(button).toBeDisabled();

    resolveConnect({ job_id: 1, repository_id: 1, status: "pending" });
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
  });
});
