# HomeKeep

Voice-first appliance care for elders: report a problem by voice with no invoice or model number, get evidence-backed checks, book a (demo) technician after explicit spoken approval, and close the case only when you confirm it is fixed.

Built for *Build, Ship, Shape: Amazon Developer Hackathon*: the Alexa+ track (self-hosted MCP server, spec 2025-11-25, Streamable HTTP) and the AWS Builder mini challenge.

> **Status:** under active development. Setup and run instructions are added as the code lands.

## Documentation
- Intent: [`intent/homekeep.md`](intent/homekeep.md)
- Business requirements: [`docs/HomeKeep_BRD_v1.0.md`](docs/HomeKeep_BRD_v1.0.md)
- Technical design (hackathon release): [`docs/HomeKeep_TDD_H_v1.0.md`](docs/HomeKeep_TDD_H_v1.0.md)
- Architecture: [`docs/architecture/homekeep_aws_architecture.png`](docs/architecture/homekeep_aws_architecture.png) and [interaction guide](docs/architecture/interactions.md)
- Delivery process: [`docs/SDLC.md`](docs/SDLC.md)

All service-provider bookings in this release are **simulated**; no real technician is dispatched. All data and the "Frostline" appliance catalog are fictional.
