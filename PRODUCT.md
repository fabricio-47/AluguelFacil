# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Multi-tenant back office for equipment and motorcycle rental businesses. Users log in through dedicated user accounts backed by the `usuarios` table (email/password, hashed via Werkzeug's `generate_password_hash`/`check_password_hash` — no bcrypt dependency in the project), attached to a specific `company_id`. Access control is governed by role-based permissions, with support for company-specific custom permissions via `permissoes_customizadas`.

## Product Purpose

AluguelFácil is the back-office system for running rental operations end to end: register clients and their identity documents, manage the rental fleet (including vehicle photos and document attachments), open and track rental agreements ("locações") with weekly or monthly recurring billing, and reconcile payments. Success is the business operator having one place to see who has which item, what's owed, and what's overdue, without juggling spreadsheets or the payment gateway's dashboard separately.

## Positioning

Rental billing is delegated to Asaas (a Brazilian payment/subscription gateway): creating a rental automatically creates a recurring Asaas subscription (boleto, weekly or monthly), and payment status/boletos sync back into the app. Multi-tenant key management allows each company to configure its own encrypted Asaas credentials and webhook secrets (`config_asaas` using Fernet encryption), with fallback to global platform credentials if unconfigured.

## Operating Context

- Server-rendered Flask + Jinja app (Bootstrap 5, Font Awesome), Portuguese (pt-BR) UI throughout.
- PostgreSQL via `psycopg2`; schema covers `usuarios`, `clientes`, `motos` (and underlying `equipment_items`), `locacoes`, `boletos`, `moto_imagens`, `servicos_locacao`, `config_asaas`, and `permissoes_customizadas`.
- Core workflows: cadastrar cliente (auto-synced to Asaas by CPF/email, enforces mandatory data updates after 90 days of inactivity) → cadastrar moto/equipamento → abrir locação (creates Asaas subscription, uploads a contract PDF, marks item indisponível) → sync/track boletos → cancelar locação (cancels Asaas subscription, frees item) → registrar serviços extras per locação.
- Document management: client registration supports 4 fixed slots — identity document front/back (`doc_frente_arquivo`, `doc_verso_arquivo`), proof of address (`comprovante_residencia_arquivo`), and customer photo (`foto_cliente_arquivo`) — plus a separate `cliente_documentos` table for open-ended extra attachments (RG, CPF, comprovante de renda, contrato, outro).
- Asaas webhook endpoint (`routes/webhook_routes.py`) accepts multi-tenant signature validation alongside manual "sincronizar boletos" pull sync.
- Deployed via `gunicorn`/`Procfile` (Render-style deployment), env-driven config (`DATABASE_URL`, `APP_ENCRYPTION_KEY`, etc.).

## Capabilities and Constraints

- Clients: create/edit, required nome/email/telefone, unique CPF/email, full document attachment workflow (identity front/back, proof of address, photo, plus open-ended extra attachments), mandatory profile recertification enforced at rental creation if idle for 90+ days (`cliente_status.py`).
- Motos / Fleet: create/edit/delete (blocked by FK if attached to a locação), single vehicle document upload, multiple photo uploads/gallery, disponível flag drives what's rentable.
- Locações: only WEEKLY or MONTHLY billing cycles (DB-constrained); one contract PDF per locação; cancel flow reverses both the Asaas subscription and the fleet item's availability.
- Payment status values are the fixed Asaas set (PENDING, RECEIVED, CONFIRMED, OVERDUE, CANCELED, REFUNDED, CHARGEBACK, RECEIVED_IN_CASH).
- Auth & RBAC: Multi-user authentication backed by `usuarios` (login, password, role, company_id). Roles and capabilities are enforced via `permissoes_customizadas` scoped per company.
- Undecided: pricing/plan model for the platform itself as a SaaS (`planos.py`/`assinaturas_routes.py` exist but their scope isn't documented here yet), and UI/localization scope for non-motorcycle equipment types now that the underlying model (`equipment_items`/`equipment_categories`) is generic.

## Brand Commitments

Product/brand name going forward is **AluguelFácil** (the repo's name).

*Note on Implementation State:* While the strategic decision is AluguelFácil, legacy branding ("MotoRental") remains present in the user interface (e.g., `templates/base.html` title, navbar-brand, and footer). Full UI string replacement is a pending development task.

## Evidence on Hand

No real customer/fleet data or contract-copy assets were found in the repo. Uploaded contracts, license docs, and photos are user-generated at runtime, not sample content to design from.

## Product Principles

1. Single source of truth: the app should stay the operator's one place to check client, fleet, and billing state — not a thin wrapper the owner still cross-checks in Asaas.
2. Money state must always be legible: pagamento_status and boleto history are load-bearing, not decorative — never bury or reformat them away.
3. Fleet availability is a hard constraint: an item's `disponivel` flag gates what can be rented, and rental creation/cancellation must keep it consistent.
4. Multi-tenant isolation: strict company-level scoping (`company_id`) must govern data access, permissions, and payment gateway credentials.
5. Portuguese-first, Brazilian back-office conventions (CPF, boleto, pt-BR dates/currency) are the default frame, not an afterthought localization.
