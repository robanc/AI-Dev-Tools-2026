# Module 2 repository guidance

This project is the AI Dev Tools Zoomcamp Module 2 collaborative coding interview MVP. These instructions apply throughout the repository.

## Specification and scope

- Read the root `product-spec.md` before making changes. Keep implementation aligned with its requirements and acceptance criteria.
- Keep the MVP small. Prefer the simplest design that satisfies the specification and modular code with focused responsibilities over large files.
- Do not implement features explicitly listed as out of scope in `product-spec.md`.
- Programming-language support and browser-side code execution remain pending decisions. Refine the specification against the homework requirements before implementing affected features; define acceptance criteria for browser-side execution if included.

## Project structure

- `frontend/`: frontend application and frontend tests.
- `backend/`: FastAPI backend and backend tests.
- `docs/`: supporting documentation.
- `openapi.yaml`: root-level OpenAPI contract for the backend API.
- `product-spec.md`: root-level product requirements, acceptance criteria, and scope.

## Dependencies and service boundaries

- Use `uv` for Python dependency management in `backend/` and to run backend commands.
- Use `npm` for dependency management and project scripts in `frontend/`.
- Keep all frontend calls to the backend centralized in one service layer, including real-time communication. UI components must use that layer rather than calling the backend directly.
- Initially use a mock implementation of the frontend service layer. Keep its interface suitable for replacing the mock with the real backend implementation.
- When adding the real backend, follow the root `openapi.yaml` contract in both the FastAPI implementation and the frontend service layer. Keep the contract and implementations consistent; document real-time message behavior in `docs/` where it is not represented by OpenAPI.

## Testing and verification

- Add tests for behavior described in `product-spec.md`, using its acceptance criteria to guide coverage. Keep frontend tests in `frontend/` and backend tests in `backend/`.
- Cover role-specific editing permissions, session creation and access, synchronization, persistence, invalid links, connection state, and reconnection as those behaviors are implemented. Enforce permissions in the backend as well as the interface.
- Verify real-time acceptance criteria with two browser windows connected to the running backend, including the specified one-second update target under normal network conditions.
- Run tests and applicable verification commands regularly, especially after meaningful changes and before committing. Use configured `npm` scripts for frontend checks and `uv run` for backend checks; document commands once tooling exists.
- Report verification results and any checks that could not be run.

## Git workflow

- Commit working checkpoints to git regularly, after relevant verification passes, with clear commit messages.
- Keep commits focused on the task and preserve unrelated user changes.
