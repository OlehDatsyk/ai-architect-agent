import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import { healthBody, interpretation, planResponse } from "./test/fixtures";
import { EXAMPLE_PROMPTS } from "./utils/examplePrompts";

const BRIEF = "A two-storey family house with three bedrooms and a garage.";
const JOB = "a".repeat(32);
const CAMERAS = [
  { name: "Camera_Exterior_Front", role: "exterior_front" },
  { name: "Camera_Interior_LivingRoom", role: "interior_livingroom" },
  { name: "Camera_FloorPlan_Ground", role: "floor_plan" },
];

function renderReply(body: { camera?: string; preset?: string; engine?: string }, id: string, note: string | null = null) {
  return new Response(JSON.stringify({
    render_id: id, image_url: `/api/designs/jobs/${JOB}/renders/${id}.png`, camera: body.camera, role: "exterior_front",
    preset: body.preset, quality: "preview", engine: body.engine === "cycles" ? "cycles" : "eevee", width: 640, height: 360,
    duration_seconds: 27, note, completed_stages: ["rendering"],
  }));
}

function buildReply() {
  return new Response(JSON.stringify({
    job_id: JOB, blend_url: `/api/designs/jobs/${JOB}/building.blend`, blender_version: "5.2.2 LTS", cameras: CAMERAS,
    object_count: 140, duration_seconds: 0.4, completed_stages: ["preparing_scene", "applying_materials", "generating_geometry", "creating_lighting", "creating_cameras"],
  }));
}

type Route = (init?: RequestInit) => Response | Promise<Response>;

/** Routes fetch calls by path so health and interpretation can be scripted independently. */
type ProjectRoute = (path: string, init?: RequestInit) => Response | Promise<Response>;

function mockApi({ configured = true, blender = "not_configured", interpret, plan, build, renders, modify, projects }: {
  configured?: boolean; blender?: "found" | "not_configured"; interpret?: Route; plan?: Route; build?: Route; renders?: Route; modify?: Route;
  projects?: ProjectRoute;
} = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const path = String(input);
    if (path.startsWith("/api/projects") && projects) return projects(path, init ?? undefined);
    if (path === "/api/designs/modify" && modify) return modify(init ?? undefined);
    if (/^\/api\/designs\/jobs\/[0-9a-f]{32}\/renders$/.test(path) && renders) return renders(init ?? undefined);
    if (path === "/api/health") return new Response(JSON.stringify(healthBody(configured, blender)));
    if (path === "/api/designs/build" && build) return build(init ?? undefined);
    if (path === "/api/designs/interpret" && interpret) return interpret(init ?? undefined);
    if (path === "/api/designs/plan" && plan) return plan(init ?? undefined);
    throw new TypeError("Failed to fetch");
  });
}

async function renderReady() {
  render(<App />);
  await screen.findByText("Connected, version 0.1.0");
  return userEvent.setup();
}

function stage(name: string) {
  const row = screen.getByText(name).closest("li");
  if (!row) throw new Error(`stage ${name} not found`);
  return within(row);
}

describe("App", () => {
  it("shows live backend status", async () => {
    mockApi();
    await renderReady();
    const system = screen.getByRole("region", { name: "System" });
    expect(within(system).getByText("Configured on the server")).toBeInTheDocument();
  });

  it("disables generation and explains why when the Claude key is missing", async () => {
    mockApi({ configured: false });
    const user = await renderReady();
    await user.type(screen.getByLabelText("Describe the building you want to create"), BRIEF);

    expect(screen.getByRole("button", { name: "Generate design" })).toBeDisabled();
    const brief = screen.getByRole("region", { name: "Brief" });
    expect(within(brief).getByText(/Add ANTHROPIC_API_KEY to .env/)).toBeInTheDocument();
  });

  it("needs a real brief before generating", async () => {
    mockApi();
    const user = await renderReady();
    expect(screen.getByRole("button", { name: "Generate design" })).toBeDisabled();
    await user.type(screen.getByLabelText("Describe the building you want to create"), BRIEF);
    expect(screen.getByRole("button", { name: "Generate design" })).toBeEnabled();
  });

  it("interprets a brief and shows the review", async () => {
    let body: unknown;
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    mockApi({
      interpret: async (init) => {
        body = JSON.parse(String(init?.body));
        await gate;
        return new Response(JSON.stringify(interpretation));
      },
    });
    const user = await renderReady();
    await user.type(screen.getByLabelText("Describe the building you want to create"), BRIEF);
    await user.click(screen.getByRole("button", { name: "Generate design" }));

    expect(await screen.findByText("Interpreting your brief")).toBeInTheDocument();
    expect(stage("Understanding request").getByText("In progress")).toBeInTheDocument();
    release();

    const review = await screen.findByRole("article", { name: "Contemporary British Family House" });
    expect(body).toEqual({ prompt: BRIEF, constraints: {} });
    expect(within(review).getByText("Master Bedroom")).toBeInTheDocument();
    expect(within(review).getByText("Assumed the second bathroom is an en-suite.")).toBeInTheDocument();
    expect(within(review).getByText(/will be enlarged to fill it/)).toBeInTheDocument();
    expect(within(review).getByRole("button", { name: "Approve and generate" })).toBeDisabled();
    expect(stage("Understanding request").getByText("Complete")).toBeInTheDocument();
    expect(stage("Rendering").getByText("Not started")).toBeInTheDocument();
  });

  it("sends advanced options as constraints", async () => {
    let body: { constraints?: Record<string, unknown> } = {};
    mockApi({ interpret: (init) => { body = JSON.parse(String(init?.body)); return new Response(JSON.stringify(interpretation)); } });
    const user = await renderReady();
    await user.type(screen.getByLabelText("Describe the building you want to create"), BRIEF);
    await user.click(screen.getByText("Advanced options"));
    await user.type(screen.getByLabelText("Bedrooms"), "4");
    await user.selectOptions(screen.getByLabelText("Roof"), "hip");
    await user.selectOptions(screen.getByLabelText("Garage"), "double");
    await user.click(screen.getByRole("button", { name: "Generate design" }));

    await screen.findByRole("article");
    expect(body.constraints).toEqual({ bedrooms: 4, roof: "hip", garage: "double" });
  });

  it("explains a failed interpretation and lists the problems", async () => {
    mockApi({
      interpret: () => new Response(JSON.stringify({
        error: {
          code: "design_interpretation_failed",
          message: "Claude returned an invalid room layout. Try rephrasing or simplifying the brief.",
          request_id: "abc",
          issues: [{ severity: "error", code: "room_inaccessible", message: "WC cannot be reached from the entrance.", element_ids: ["wc"], location: null }],
        },
      }), { status: 422 }),
    });
    const user = await renderReady();
    await user.type(screen.getByLabelText("Describe the building you want to create"), BRIEF);
    await user.click(screen.getByRole("button", { name: "Generate design" }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/Claude returned an invalid room layout/)).toBeInTheDocument();
    expect(within(alert).getByText("WC cannot be reached from the entrance.")).toBeInTheDocument();
    expect(stage("Understanding request").getByText("Failed")).toBeInTheDocument();
  });

  it("edit brief returns focus to the brief", async () => {
    mockApi({ interpret: () => new Response(JSON.stringify(interpretation)) });
    const user = await renderReady();
    const textarea = screen.getByLabelText("Describe the building you want to create");
    await user.type(textarea, BRIEF);
    await user.click(screen.getByRole("button", { name: "Generate design" }));
    await user.click(await screen.findByRole("button", { name: "Edit brief" }));
    expect(textarea).toHaveFocus();
    expect(textarea).toHaveValue(BRIEF);
  });

  it("fills an example prompt and clears it", async () => {
    mockApi();
    const user = await renderReady();
    const textarea = screen.getByLabelText("Describe the building you want to create");
    await user.click(screen.getByRole("button", { name: "Example prompt" }));
    expect(textarea).toHaveValue(EXAMPLE_PROMPTS[0]);
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(textarea).toHaveValue("");
  });

  it("lays out the interpreted design and shows its floor plans", async () => {
    let planBody: { intent?: { project_name?: string } } = {};
    mockApi({
      interpret: () => new Response(JSON.stringify(interpretation)),
      plan: (init) => { planBody = JSON.parse(String(init?.body)); return new Response(JSON.stringify(planResponse)); },
    });
    const user = await renderReady();
    await user.type(screen.getByLabelText("Describe the building you want to create"), BRIEF);
    await user.click(screen.getByRole("button", { name: "Generate design" }));

    const ground = await screen.findByRole("img", { name: "Ground floor plan" });
    expect(planBody.intent?.project_name).toBe("Contemporary British Family House");
    expect(ground.getAttribute("src")).toMatch(/^data:image\/svg\+xml/);

    await user.click(screen.getByRole("tab", { name: "First floor" }));
    expect(screen.getByRole("img", { name: "First floor plan" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "First floor" })).toHaveAttribute("aria-selected", "true");

    const review = screen.getByRole("article");
    expect(within(review).getByText(/Merged Upper Corridor into Landing/)).toBeInTheDocument();
    expect(within(review).getByText(/En-suite is 2.9 m²/)).toBeInTheDocument();
    expect(within(review).getByText("163 m²")).toBeInTheDocument();
    for (const name of ["Understanding request", "Planning rooms", "Creating architectural specification", "Validating design"]) {
      expect(stage(name).getByText("Complete")).toBeInTheDocument();
    }
    expect(stage("Preparing Blender scene").getByText("Not started")).toBeInTheDocument();
  });

  it("never puts plan markup into the page, so scripts in it cannot run", async () => {
    mockApi({ interpret: () => new Response(JSON.stringify(interpretation)), plan: () => new Response(JSON.stringify(planResponse)) });
    const user = await renderReady();
    await user.type(screen.getByLabelText("Describe the building you want to create"), BRIEF);
    await user.click(screen.getByRole("button", { name: "Generate design" }));
    await screen.findByRole("img", { name: "Ground floor plan" });
    expect(document.querySelector("script")).toBeNull();
    expect(document.querySelector("article svg text")).toBeNull();
  });

  it("keeps the interpretation when the floor plan cannot be laid out", async () => {
    mockApi({
      interpret: () => new Response(JSON.stringify(interpretation)),
      plan: () => new Response(JSON.stringify({ error: { code: "planning_failed", message: "The footprint is 4.6 m deep, but a straight stair needs about 5.1 m. Make the building deeper.", request_id: "r" } }), { status: 422 }),
    });
    const user = await renderReady();
    await user.type(screen.getByLabelText("Describe the building you want to create"), BRIEF);
    await user.click(screen.getByRole("button", { name: "Generate design" }));

    const review = await screen.findByRole("article", { name: "Contemporary British Family House" });
    const alert = await within(review).findByRole("alert");
    expect(within(alert).getByText(/Make the building deeper/)).toBeInTheDocument();
    expect(within(review).getByText("Master Bedroom")).toBeInTheDocument();
    expect(stage("Understanding request").getByText("Complete")).toBeInTheDocument();
    expect(stage("Planning rooms").getByText("Failed")).toBeInTheDocument();
  });

  async function generateWithPlan(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText("Describe the building you want to create"), BRIEF);
    await user.click(screen.getByRole("button", { name: "Generate design" }));
    await screen.findByRole("img", { name: "Ground floor plan" });
  }

  it("builds the approved design in Blender and offers the .blend file", async () => {
    let sent: { specification?: unknown } = {};
    mockApi({
      blender: "found",
      renders: (init) => renderReply(JSON.parse(String(init?.body)), "e".repeat(32)),
      interpret: () => new Response(JSON.stringify(interpretation)),
      plan: () => new Response(JSON.stringify({ ...planResponse, specification: { schema_version: "1.0" } })),
      build: (init) => {
        sent = JSON.parse(String(init?.body));
        return new Response(JSON.stringify({
          job_id: "a".repeat(32), blend_url: `/api/designs/jobs/${"a".repeat(32)}/building.blend`, blender_version: "5.2.2 LTS",
          cameras: CAMERAS,
          object_count: 51, duration_seconds: 0.67, completed_stages: ["preparing_scene", "applying_materials", "generating_geometry", "creating_lighting", "creating_cameras"],
        }));
      },
    });
    const user = await renderReady();
    await generateWithPlan(user);
    await user.click(screen.getByRole("button", { name: "Approve and generate" }));

    expect(await screen.findByText(/Built in Blender 5.2.2 LTS: 51 objects/)).toBeInTheDocument();
    expect(sent.specification).toEqual({ schema_version: "1.0" });
    const link = screen.getByRole("link", { name: "Download the .blend file" });
    expect(link).toHaveAttribute("href", `/api/designs/jobs/${"a".repeat(32)}/building.blend`);
    expect(stage("Preparing Blender scene").getByText("Complete")).toBeInTheDocument();
    expect(stage("Generating geometry").getByText("Complete")).toBeInTheDocument();
    expect(stage("Applying materials").getByText("Complete")).toBeInTheDocument();
    expect(stage("Creating lighting").getByText("Complete")).toBeInTheDocument();
    expect(stage("Creating cameras").getByText("Complete")).toBeInTheDocument();
    // Every build is followed by an automatic preview render.
    expect(await screen.findByRole("img", { name: "Exterior front render, day lighting" })).toBeInTheDocument();
    expect(stage("Rendering").getByText("Complete")).toBeInTheDocument();
  });

  it("explains that Blender must be configured before building", async () => {
    mockApi({ blender: "not_configured", interpret: () => new Response(JSON.stringify(interpretation)), plan: () => new Response(JSON.stringify(planResponse)) });
    const user = await renderReady();
    await generateWithPlan(user);
    expect(screen.getByRole("button", { name: "Approve and generate" })).toBeDisabled();
    expect(within(screen.getByRole("article")).getByText(/Set BLENDER_EXECUTABLE in .env/)).toBeInTheDocument();
  });

  it("reports a failed Blender build", async () => {
    mockApi({
      blender: "found",
      interpret: () => new Response(JSON.stringify(interpretation)),
      plan: () => new Response(JSON.stringify(planResponse)),
      build: () => new Response(JSON.stringify({ error: { code: "blender_timeout", message: "Blender did not finish within 300 seconds.", request_id: "r" } }), { status: 504 }),
    });
    const user = await renderReady();
    await generateWithPlan(user);
    await user.click(screen.getByRole("button", { name: "Approve and generate" }));
    expect(await screen.findByText("Blender did not finish within 300 seconds.")).toBeInTheDocument();
    expect(stage("Preparing Blender scene").getByText("Failed")).toBeInTheDocument();
  });

  async function buildDesign(user: ReturnType<typeof userEvent.setup>) {
    await generateWithPlan(user);
    await user.click(screen.getByRole("button", { name: "Approve and generate" }));
  }

  it("renders a preview automatically after building", async () => {
    const requests: unknown[] = [];
    mockApi({
      blender: "found", build: buildReply,
      interpret: () => new Response(JSON.stringify(interpretation)), plan: () => new Response(JSON.stringify(planResponse)),
      renders: (init) => { const body = JSON.parse(String(init?.body)); requests.push(body); return renderReply(body, "c".repeat(32)); },
    });
    const user = await renderReady();
    await buildDesign(user);

    const image = await screen.findByRole("img", { name: "Exterior front render, day lighting" });
    expect(image).toHaveAttribute("src", `/api/designs/jobs/${JOB}/renders/${"c".repeat(32)}.png`);
    expect(requests).toEqual([{ camera: "Camera_Exterior_Front", preset: "day", quality: "preview", resolution: "1280x720", engine: "auto" }]);
    expect(screen.getByText(/Exterior front, day, preview, EEVEE, 640 x 360, 27 s/)).toBeInTheDocument();
    expect(stage("Rendering").getByText("Complete")).toBeInTheDocument();
  });

  it("renders a chosen camera, lighting and quality", async () => {
    const requests: { camera: string; preset: string; quality: string; engine: string }[] = [];
    let n = 0;
    mockApi({
      blender: "found", build: buildReply,
      interpret: () => new Response(JSON.stringify(interpretation)), plan: () => new Response(JSON.stringify(planResponse)),
      renders: (init) => { const body = JSON.parse(String(init?.body)); requests.push(body); n += 1; return renderReply(body, String(n).repeat(32), body.engine === "cycles" ? null : null); },
    });
    const user = await renderReady();
    await buildDesign(user);
    await screen.findByRole("img", { name: "Exterior front render, day lighting" });

    await user.selectOptions(screen.getByLabelText("Camera"), "Camera_FloorPlan_Ground");
    await user.selectOptions(screen.getByLabelText("Lighting"), "evening");
    await user.selectOptions(screen.getByLabelText("Quality"), "standard");
    await user.selectOptions(screen.getByLabelText("Engine"), "cycles");
    await user.click(screen.getByRole("button", { name: "Render" }));

    expect(await screen.findByRole("img", { name: "Floor plan ground render, evening lighting" })).toBeInTheDocument();
    expect(requests[1]).toMatchObject({ camera: "Camera_FloorPlan_Ground", preset: "evening", quality: "standard", engine: "cycles" });
    expect(screen.getAllByRole("img", { name: /render,/ })).toHaveLength(2);  // newest first, earlier renders kept
  });

  it("explains why a render fell back to Cycles", async () => {
    mockApi({
      blender: "found", build: buildReply,
      interpret: () => new Response(JSON.stringify(interpretation)), plan: () => new Response(JSON.stringify(planResponse)),
      renders: (init) => renderReply({ ...JSON.parse(String(init?.body)), engine: "cycles" }, "d".repeat(32),
        "EEVEE is not available on this machine (it needs OpenGL), so Cycles was used."),
    });
    const user = await renderReady();
    await buildDesign(user);
    expect(await screen.findByText(/so Cycles was used/)).toBeInTheDocument();
  });

  it("reports a failed render", async () => {
    mockApi({
      blender: "found", build: buildReply,
      interpret: () => new Response(JSON.stringify(interpretation)), plan: () => new Response(JSON.stringify(planResponse)),
      renders: () => new Response(JSON.stringify({ error: { code: "render_timeout", message: "The render did not finish within 900 seconds.", request_id: "r" } }), { status: 504 }),
    });
    const user = await renderReady();
    await buildDesign(user);
    expect(await screen.findByText("The render did not finish within 900 seconds.")).toBeInTheDocument();
    expect(stage("Rendering").getByText("Failed")).toBeInTheDocument();
  });

  it("changes the design in plain English and shows what changed", async () => {
    const bodies: { request: string; overrides: unknown[]; intent: { project_name: string }; specification: unknown }[] = [];
    mockApi({
      interpret: () => new Response(JSON.stringify(interpretation)),
      plan: () => new Response(JSON.stringify({ ...planResponse, specification: { version: "before" } })),
      modify: (init) => {
        const body = JSON.parse(String(init?.body)); bodies.push(body);
        return new Response(JSON.stringify({
          ...planResponse, specification: { version: `after-${bodies.length}` }, intent: interpretation.intent,
          overrides: [...body.overrides, { op: "set_exterior_material", params: { surface: "wall", material: "brick", colour: "#A33A2A" } }],
          change_summary: "Red brick walls.", changes: ["Exterior wall: brick -> brick (#A33A2A)."], assumptions: ["Red means a warm mid red."],
          attempts: 1, model: "claude-sonnet-5-5", plans: [{ level: 0, name: "Ground floor", svg: "<svg xmlns='http://www.w3.org/2000/svg'/>" }],
        }));
      },
    });
    const user = await renderReady();
    await generateWithPlan(user);
    await user.type(screen.getByLabelText("Describe a change"), "Change the exterior to red brick");
    await user.click(screen.getByRole("button", { name: "Apply change" }));

    expect(await screen.findByText("Exterior wall: brick -> brick (#A33A2A).")).toBeInTheDocument();
    expect(screen.getByText(/What changed: Red brick walls./)).toBeInTheDocument();
    expect(screen.getByText(/Assumed: Red means a warm mid red./)).toBeInTheDocument();
    expect(bodies[0]).toMatchObject({ request: "Change the exterior to red brick", overrides: [], specification: { version: "before" } });
    expect(screen.getByLabelText("Describe a change")).toHaveValue("");

    // The next change is made to the updated design, carrying the overrides forward.
    await user.type(screen.getByLabelText("Describe a change"), "Add a window to the master bedroom");
    await user.click(screen.getByRole("button", { name: "Apply change" }));
    await screen.findByText("All changes (2)");
    expect(bodies[1]).toMatchObject({ specification: { version: "after-1" }, overrides: [{ op: "set_exterior_material" }] });
  });

  it("explains a change that could not be applied", async () => {
    mockApi({
      interpret: () => new Response(JSON.stringify(interpretation)), plan: () => new Response(JSON.stringify(planResponse)),
      modify: () => new Response(JSON.stringify({ error: { code: "modification_failed", message: "The change could not be applied to this design: There is no free wall space for another window in WC.", request_id: "r" } }), { status: 422 }),
    });
    const user = await renderReady();
    await generateWithPlan(user);
    await user.type(screen.getByLabelText("Describe a change"), "Add a window to the WC");
    await user.click(screen.getByRole("button", { name: "Apply change" }));
    expect(await screen.findByText(/no free wall space for another window in WC/)).toBeInTheDocument();
    expect(screen.getByLabelText("Describe a change")).toHaveValue("Add a window to the WC");  // kept, so it can be edited
  });

  function modifyReply(body: { overrides: unknown[] }) {
    return new Response(JSON.stringify({
      ...planResponse, specification: { version: "after" }, intent: interpretation.intent,
      overrides: [...body.overrides, { op: "set_roof", params: {} }], change_summary: "Hip roof.",
      changes: ["Roof: gable 35° slate -> hip 35° slate."], assumptions: [], attempts: 1, model: "claude-sonnet-5-5",
    }));
  }

  function savedProject(id: string, version: number, body: Record<string, unknown>) {
    return new Response(JSON.stringify({ ...body, id, version, updated_at: "2026-10-04T12:00:00Z" }), { status: version === 1 ? 201 : 200 });
  }

  it("saves a project, notices changes, and saves again as a new version", async () => {
    const calls: { method: string; path: string; body: Record<string, unknown> }[] = [];
    mockApi({
      interpret: () => new Response(JSON.stringify(interpretation)),
      plan: () => new Response(JSON.stringify({ ...planResponse, specification: { version: "before" } })),
      modify: (init) => modifyReply(JSON.parse(String(init?.body))),
      projects: (path, init) => {
        const method = init?.method ?? "GET";
        if (method === "GET") return new Response("[]");
        const body = JSON.parse(String(init?.body));
        calls.push({ method, path, body });
        return savedProject("f".repeat(32), method === "POST" ? 1 : 2, body);
      },
    });
    const user = await renderReady();
    await generateWithPlan(user);
    expect(screen.getByText("Not saved yet")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Project name"));
    await user.type(screen.getByLabelText("Project name"), "Smith house");
    await user.click(screen.getByRole("button", { name: "Save project" }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(calls[0]).toMatchObject({ method: "POST", path: "/api/projects", body: { name: "Smith house", brief: BRIEF, specification: { version: "before" }, history: [] } });

    await user.type(screen.getByLabelText("Describe a change"), "Change the roof to a hip roof");
    await user.click(screen.getByRole("button", { name: "Apply change" }));
    expect(await screen.findByText("Unsaved changes")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save project" }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(calls[1]).toMatchObject({ method: "PUT", path: `/api/projects/${"f".repeat(32)}`, body: { version: 1, specification: { version: "after" } } });
    expect((calls[1]!.body.history as unknown[]).length).toBe(1);
  });

  it("reopens a saved project with its plans, build and renders", async () => {
    const id = "e".repeat(32);
    const renderPosts: unknown[] = [];
    const project = {
      id, version: 3, name: "Smith house", updated_at: "2026-10-04T12:00:00Z", brief: BRIEF, constraints: { bedrooms: 3 },
      interpretation, intent: interpretation.intent, overrides: [], specification: { version: "saved" },
      report: planResponse.report, notes: [], summary: planResponse.summary, plans: planResponse.plans,
      history: [{ request: "Change the roof to a hip roof", summary: "Hip roof.", changes: ["Roof: gable 35° slate -> hip 35° slate."], assumptions: [] }],
      build: { job_id: JOB, blender_version: "5.2.2 LTS", object_count: 140, cameras: CAMERAS, blend_url: `/api/designs/jobs/${JOB}/building.blend`, blend_path: "x", available: true },
      renders: [{ render_id: "c".repeat(32), job_id: JOB, camera: "Camera_Exterior_Front", preset: "day", quality: "preview", engine: "cycles",
                  width: 640, height: 360, note: null, image_url: `/api/designs/jobs/${JOB}/renders/${"c".repeat(32)}.png`, image_path: "x", available: true }],
    };
    mockApi({
      blender: "found",
      renders: (init) => { renderPosts.push(init); return renderReply({}, "d".repeat(32)); },
      projects: (path) => path === "/api/projects"
        ? new Response(JSON.stringify([{ id, name: "Smith house", version: 3, updated_at: project.updated_at, floors: 2, bedrooms: 3, changes: 1, thumbnail_url: null }]))
        : new Response(JSON.stringify(project)),
    });
    const user = await renderReady();
    await user.click(await screen.findByRole("button", { name: "Open Smith house" }));

    expect(await screen.findByRole("article", { name: "Contemporary British Family House" })).toBeInTheDocument();
    expect(screen.getByLabelText("Describe the building you want to create")).toHaveValue(BRIEF);
    expect(screen.getByLabelText("Project name")).toHaveValue("Smith house");
    expect(screen.getByRole("img", { name: "Ground floor plan" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Exterior front render, day lighting" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download the .blend file" })).toBeInTheDocument();
    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(renderPosts).toHaveLength(0);  // no fresh preview: the saved renders were restored
  });

  it("explains a save that conflicts with a newer version", async () => {
    mockApi({
      interpret: () => new Response(JSON.stringify(interpretation)), plan: () => new Response(JSON.stringify(planResponse)),
      projects: (_path, init) => (init?.method ?? "GET") === "GET" ? new Response("[]")
        : new Response(JSON.stringify({ error: { code: "project_changed", message: "This project was saved elsewhere since you opened it. Reopen it to see the latest version.", request_id: "r", current_version: 4 } }), { status: 409 }),
    });
    const user = await renderReady();
    await generateWithPlan(user);
    await user.click(screen.getByRole("button", { name: "Save project" }));
    expect(await screen.findByText(/saved elsewhere since you opened it/)).toBeInTheDocument();
  });

  it("shows validation problems with the rooms they affect", async () => {
    const failing = {
      ...planResponse,
      specification: { rooms: [{ id: "wc", name: "WC" }, { id: "kitchen", name: "Kitchen" }] },
      report: {
        status: "ERROR", error_count: 1, warning_count: 1,
        issues: [
          { severity: "error", code: "room_overlap", message: "WC overlaps Kitchen by 1.40 m².", element_ids: ["wc", "kitchen"], location: null },
          { severity: "warning", code: "room_small", message: "WC is below the typical size.", element_ids: ["wc"], location: null },
        ],
        fixes: [{ code: "stair_rise_corrected", message: "Set the stair rise to 193 mm.", element_ids: [] }],
      },
    };
    mockApi({ interpret: () => new Response(JSON.stringify(interpretation)), plan: () => new Response(JSON.stringify(failing)) });
    const user = await renderReady();
    await generateWithPlan(user);
    const checks = screen.getByRole("region", { name: "Design checks" });
    expect(within(checks).getByText("Has problems that must be fixed")).toBeInTheDocument();
    expect(within(checks).getByText("WC overlaps Kitchen by 1.40 m².")).toBeInTheDocument();
    expect(within(checks).getByText("Affects: WC, Kitchen")).toBeInTheDocument();
    expect(within(checks).getByText("Set the stair rise to 193 mm.")).toBeInTheDocument();
  });

  it("does not count unset advanced options in a reopened project as set", async () => {
    const id = "9".repeat(32);
    const project = {
      id, version: 1, name: "Plain", updated_at: "2026-10-04T12:00:00Z", brief: BRIEF,
      constraints: { building_type: null, style: null, floors: null, width: null, depth: null, height: null, bedrooms: 4, bathrooms: null, garage: null, roof: "automatic", detail_level: "standard" },
      interpretation, intent: interpretation.intent, overrides: [], specification: {}, report: planResponse.report, notes: [],
      summary: planResponse.summary, plans: planResponse.plans, history: [], build: null, renders: [],
    };
    mockApi({ projects: (path) => path === "/api/projects"
      ? new Response(JSON.stringify([{ id, name: "Plain", version: 1, updated_at: project.updated_at, floors: 2, bedrooms: 4, changes: 0, thumbnail_url: null }]))
      : new Response(JSON.stringify(project)) });
    const user = await renderReady();
    await user.click(await screen.findByRole("button", { name: "Open Plain" }));
    await screen.findByRole("article");
    expect(screen.getByText("1 set")).toBeInTheDocument();  // only "bedrooms", not the nine stored nulls
  });

  it("explains a Claude billing error clearly, with Anthropic's reason in development", async () => {
    mockApi({
      interpret: () => new Response(JSON.stringify({ error: {
        code: "CLAUDE_BILLING_ERROR", message: "Your Anthropic account has no API credit.", request_id: "r",
        reason: "Your credit balance is too low to access the Anthropic API." } }), { status: 402 }),
    });
    const user = await renderReady();
    await user.type(screen.getByLabelText("Describe the building you want to create"), BRIEF);
    await user.click(screen.getByRole("button", { name: "Generate design" }));
    expect(await screen.findByText(/Add credit at console.anthropic.com/)).toBeInTheDocument();
    expect(screen.getByText(/Anthropic said: "Your credit balance is too low/)).toBeInTheDocument();
  });

  it("verifies the Claude connection from the System panel", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = String(input);
      calls.push(path);
      if (path === "/api/health") return new Response(JSON.stringify(healthBody(true)));
      if (path.startsWith("/api/health/claude")) return new Response(JSON.stringify({
        status: "failed", structured_outputs: "not_checked", code: "CLAUDE_MODEL_ERROR",
        message: "The configured Claude model is unavailable. Check ANTHROPIC_MODEL in .env.", checked_at: "2026-10-06T09:00:00Z" }));
      throw new TypeError("network");
    });
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByText("Not checked")).toBeInTheDocument();
    expect(screen.getByText("Model: claude-sonnet-5-5")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/configured Claude model is unavailable/)).toBeInTheDocument();
    expect(calls).toContain("/api/health/claude?refresh=true");
  });
});
