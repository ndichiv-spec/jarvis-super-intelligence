import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: apiGet, post: vi.fn() },
}));

import GeographyPage from "./page";

const providers = {
  geocoding: { configured: true, user_agent_configured: true },
  routing: { configured: true },
  satellite_imagery: {
    configured: true,
    provider_license_confirmed: false,
    license_confirmed: false,
  },
  attribution: "Configured map and geocoding services",
};
const originalGeolocation = Object.getOwnPropertyDescriptor(navigator, "geolocation");

describe("Geospatial Vision", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiGet.mockResolvedValue(providers);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    if (originalGeolocation) {
      Object.defineProperty(navigator, "geolocation", originalGeolocation);
    } else {
      Reflect.deleteProperty(navigator, "geolocation");
    }
  });

  it("requests a one-shot browser location only after the user clicks and displays its actual coordinates", async () => {
    const getCurrentPosition = vi.fn();
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition },
    });

    render(<GeographyPage />);

    expect(getCurrentPosition).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Use my location" }));
    expect(getCurrentPosition).toHaveBeenCalledTimes(1);
    expect(getCurrentPosition).toHaveBeenCalledWith(
      expect.any(Function),
      expect.any(Function),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );

    const onSuccess = getCurrentPosition.mock.calls[0][0] as (position: GeolocationPosition) => void;
    onSuccess({
      coords: { latitude: 47.6062, longitude: -122.3321, accuracy: 18 },
    } as GeolocationPosition);

    expect(await screen.findByText("47.606200, -122.332100")).toBeInTheDocument();
    expect(screen.getByText("Reported accuracy: ±18 m")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTitle("OpenStreetMap location map")).toHaveAttribute("src", expect.stringContaining("marker="));
    });
    expect(screen.getByText("Satellite imagery", { selector: "dt" }).parentElement).toHaveTextContent("Unavailable");
  });

  it("explains when browser geolocation is unavailable without requesting it automatically", async () => {
    Object.defineProperty(navigator, "geolocation", { configurable: true, value: undefined });
    render(<GeographyPage />);

    expect(await screen.findByText("Search uses the configured geocoding provider.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use my location" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("This browser does not provide location services.");
  });

  it.each([
    [1, "Location permission was denied."],
    [2, "Your position is currently unavailable."],
    [3, "The location request timed out."],
  ])("shows a clear message when browser location returns error %i", async (code, message) => {
    const getCurrentPosition = vi.fn();
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition },
    });
    render(<GeographyPage />);

    fireEvent.click(screen.getByRole("button", { name: "Use my location" }));
    const onError = getCurrentPosition.mock.calls[0][1] as (error: GeolocationPositionError) => void;
    onError({
      code,
      message: "Location request failed",
      PERMISSION_DENIED: 1,
      POSITION_UNAVAILABLE: 2,
      TIMEOUT: 3,
    } as GeolocationPositionError);

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });
});
