import { render, screen } from "@testing-library/react";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders a readable label for a completed run", () => {
    render(<StatusBadge status="completed" />);

    expect(screen.getByText("已完成")).toBeInTheDocument();
  });

  it("distinguishes a limited completion from a failure", () => {
    const { rerender } = render(
      <StatusBadge status="completed_with_limitations" />,
    );
    expect(screen.getByText("有限完成")).toBeInTheDocument();

    rerender(<StatusBadge status="failed" />);
    expect(screen.getByText("失败")).toBeInTheDocument();
  });

  it("renders a cancelled run as a terminal state", () => {
    render(<StatusBadge status="cancelled" />);

    expect(screen.getByText("已取消")).toBeInTheDocument();
  });
});
