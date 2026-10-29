import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { BandBadge, ConfirmDialog, Pagination, ProgressBar } from "../components/ui";
import { fmtDate, fmtNumber } from "../lib/format";
import ForgotPassword from "../pages/ForgotPassword";
import ResetPassword from "../pages/ResetPassword";

describe("ui pieces", () => {
  it("labels confidence bands in plain words", () => {
    render(<BandBadge band="unmatched" />);
    expect(screen.getByText("No match")).toBeInTheDocument();
  });
  it("clamps the progress bar", () => {
    render(<ProgressBar value={140} label="x" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  });
  it("confirm dialog stays disabled until allowed and calls back", () => {
    const onConfirm = vi.fn();
    const { rerender } = render(<ConfirmDialog open title="Delete?" disabled onConfirm={onConfirm} onClose={() => {}}>Sure?</ConfirmDialog>);
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
    rerender(<ConfirmDialog open title="Delete?" onConfirm={onConfirm} onClose={() => {}}>Sure?</ConfirmDialog>);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });
  it("closes the dialog with Escape", () => {
    const onClose = vi.fn();
    render(<ConfirmDialog open title="T" onConfirm={() => {}} onClose={onClose}>x</ConfirmDialog>);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
  it("pagination moves between pages", () => {
    const onPage = vi.fn();
    render(<Pagination page={2} pageSize={10} count={35} onPage={onPage} />);
    fireEvent.click(screen.getByText("Next"));
    expect(onPage).toHaveBeenCalledWith(3);
    fireEvent.click(screen.getByText("Previous"));
    expect(onPage).toHaveBeenCalledWith(1);
  });
  it("formats numbers and missing dates safely", () => {
    expect(fmtNumber(null)).toBe("0");
    expect(fmtDate(null)).toBe("—");
    expect(fmtDate("not a date")).toBe("—");
  });
});

describe("password pages", () => {
  it("reset page explains a broken link instead of showing a form", () => {
    render(<MemoryRouter initialEntries={["/reset-password"]}><ResetPassword /></MemoryRouter>);
    expect(screen.getByText(/incomplete/i)).toBeInTheDocument();
  });
  it("forgot page keeps the button disabled until an email is typed", () => {
    render(<MemoryRouter><ForgotPassword /></MemoryRouter>);
    expect(screen.getByRole("button", { name: /send reset link/i })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.co" } });
    expect(screen.getByRole("button", { name: /send reset link/i })).toBeEnabled();
  });
});
