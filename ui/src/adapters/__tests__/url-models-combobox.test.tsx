// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the API client so tests don't need a real backend.
vi.mock("../../api/agents", () => ({
  agentsApi: {
    adapterModels: vi.fn(),
  },
}));

// Mock the CompanyContext hook so tests don't need a full provider tree.
vi.mock("../../context/CompanyContext", () => ({
  useCompany: () => ({ selectedCompanyId: "test-company-id" }),
}));

import { SchemaConfigFields } from "../schema-config-fields";
import { agentsApi } from "../../api/agents";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const mockSchema = {
  version: 1,
  fields: [
    { key: "url", label: "LM Studio URL", type: "text", default: "http://primary:1234" },
    {
      key: "defaultModel",
      label: "Modell",
      type: "combobox",
      meta: { optionsFromUrlField: "url" },
    },
    { key: "fallbackUrl", label: "Fallback URL", type: "text" },
    {
      key: "fallbackModel",
      label: "Fallback-Modell",
      type: "combobox",
      meta: { optionsFromUrlField: "fallbackUrl", disabledWhenEmpty: "fallbackUrl" },
    },
  ],
};

// Intercept the config-schema fetch that SchemaConfigFields does internally.
// Also clear the module-level caches in schema-config-fields.tsx between tests.
async function primeSchemaCache() {
  const mod = await import("../schema-config-fields");
  mod.invalidateConfigSchemaCache("lmstudio_local");
}

beforeEach(async () => {
  vi.clearAllMocks();
  await primeSchemaCache();
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/config-schema")) {
      return new Response(JSON.stringify(mockSchema), { status: 200 });
    }
    return new Response("{}", { status: 404 });
  }) as unknown as typeof fetch;
});

afterEach(async () => {
  await primeSchemaCache();
});

async function renderAndWaitForSchema(overrides: {
  fallbackUrl?: string;
} = {}): Promise<{ container: HTMLDivElement; root: Root }> {
  const container = document.createElement("div");
  document.body.appendChild(container);

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const values = {
    adapterSchemaValues: {
      url: "http://primary:1234",
      fallbackUrl: overrides.fallbackUrl ?? "",
    },
  };
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <SchemaConfigFields
          mode="create"
          adapterType="lmstudio_local"
          isCreate
          values={values as never}
          set={vi.fn()}
          config={{}}
          eff={(_g, _f, d) => d as never}
          mark={vi.fn()}
          models={[]}
        />
      </QueryClientProvider>,
    );
  });

  // Allow the async schema fetch effect to resolve and rerender.
  for (let i = 0; i < 10; i++) {
    await act(async () => {
      await Promise.resolve();
    });
    if (container.querySelector("input")) break;
  }

  return { container, root };
}

function findComboboxInputByLabel(
  container: HTMLElement,
  label: string,
): HTMLInputElement | null {
  // Field renders:
  //   <div>
  //     <div class="flex..."><label>{label}</label>...</div>
  //     {children}  ← ComboboxField here
  //   </div>
  const labels = Array.from(container.querySelectorAll("label"));
  const labelEl = labels.find((l) => (l.textContent ?? "").trim() === label);
  if (!labelEl) return null;
  // The label is inside a header row; the input lives as a later sibling of
  // that row's parent (the Field wrapper div).
  const fieldWrapper = labelEl.parentElement?.parentElement;
  if (!fieldWrapper) return null;
  return fieldWrapper.querySelector<HTMLInputElement>("input");
}

describe("SchemaConfigFields with optionsFromUrlField", () => {
  afterEach(() => {
    // Clean up DOM nodes added during tests
    document.body.innerHTML = "";
  });

  it("does not fetch models until user opens the dropdown", async () => {
    (agentsApi.adapterModels as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    const { root } = await renderAndWaitForSchema();

    // Give React-Query a tick to confirm no fetch was fired.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });

    expect(agentsApi.adapterModels).not.toHaveBeenCalled();

    act(() => {
      root.unmount();
    });
  });

  it("fetches with current url value when the combobox opens", async () => {
    (agentsApi.adapterModels as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "qwen", label: "qwen" },
    ]);
    const { container, root } = await renderAndWaitForSchema();

    const modellInput = findComboboxInputByLabel(container, "Modell");
    expect(modellInput).toBeTruthy();

    // Focusing the ComboboxField's input triggers onOpenChange(true), which
    // flips hasOpened → true and enables the React-Query fetch.
    await act(async () => {
      modellInput!.focus();
    });

    // Allow React-Query to kick off the fetch.
    for (let i = 0; i < 20; i++) {
      await act(async () => {
        await new Promise((r) => setTimeout(r, 10));
      });
      if ((agentsApi.adapterModels as ReturnType<typeof vi.fn>).mock.calls.length > 0) break;
    }

    expect(agentsApi.adapterModels).toHaveBeenCalledWith(
      "test-company-id",
      "lmstudio_local",
      "http://primary:1234",
    );

    act(() => {
      root.unmount();
    });
  });

  it("disables fallbackModel when fallbackUrl is empty", async () => {
    (agentsApi.adapterModels as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    const { container, root } = await renderAndWaitForSchema({ fallbackUrl: "" });

    const fallbackInput = findComboboxInputByLabel(container, "Fallback-Modell");
    expect(fallbackInput).toBeTruthy();
    expect(fallbackInput!.disabled).toBe(true);

    act(() => {
      root.unmount();
    });
  });
});
