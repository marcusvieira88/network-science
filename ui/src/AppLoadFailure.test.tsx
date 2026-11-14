import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "@/App";

describe("App when the release data cannot be loaded", () => {
  it("shows the loader's message in an alert instead of the explorer", async () => {
    const message = "release.json could not be loaded (HTTP 500)";
    render(<App load={() => Promise.resolve({ status: "error", message })} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The release data could not be loaded");
    expect(alert).toHaveTextContent(message);
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
