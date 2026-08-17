# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Solo owner-operator of a motorcycle rental business. One person runs client intake, fleet management, and rental/billing from this back office — there is currently a single hardcoded admin login (`admin`/`admin` via Flask-Login), with no multi-user or role model yet.

## Product Purpose

AluguelFácil is the back-office system for running a motorcycle rental operation end to end: register clients and their driver's-license documents, manage the motorcycle fleet (including per-bike photos and vehicle documents), open and track rental agreements ("locações") with weekly or monthly recurring billing, and reconcile payments. Success is the owner having one place to see who has which bike, what's owed, and what's overdue, without juggling spreadsheets or the payment gateway's dashboard separately.

## Positioning

Rental billing is delegated to Asaas (a Brazilian payment/subscription gateway): creating a rental automatically creates a recurring Asaas subscription (boleto, weekly or monthly), and payment status/boletos sync back into the app. The app is the operational system of record; Asaas is the money-movement and collections engine behind it.

## Operating Context

- Server-rendered Flask + Jinja app (Bootstrap 5, Font Awesome), Portuguese (pt-BR) UI throughout.
- PostgreSQL via `psycopg2`; schema covers `usuarios`, `clientes`, `motos`, `locacoes`, `boletos`, `moto_imagens`, `servicos_locacao`.
- Core workflows: cadastrar cliente (auto-synced to Asaas by CPF/email) → cadastrar moto → abrir locação (creates Asaas subscription, uploads a single contract PDF, marks the moto indisponível) → sync/track boletos → cancelar locação (cancels the Asaas subscription, frees the moto) → registrar serviços extras (maintenance/km) per locação.
- File uploads live on local disk under `uploads/{contratos,habilitacoes,motos}`, served back through authenticated routes.
- Asaas webhook endpoint exists (`routes/webhook_routes.py`) for payment status push updates, alongside manual "sincronizar boletos" pull sync.
- Deployed via `gunicorn`/`Procfile` (Render-style deployment), env-driven config (`DATABASE_URL`, `ASAAS_API_KEY`, etc.).

## Capabilities and Constraints

- Clients: create/edit, required nome/email/telefone, unique CPF/email, driver's-license file field (`habilitacao_arquivo`) present in schema though no dedicated upload route was found for it yet.
- Motos: create/edit/delete (blocked by FK if attached to a locação), single vehicle document upload, multiple photo uploads/gallery, disponível flag drives what's rentable.
- Locações: only WEEKLY or MONTHLY billing cycles (DB-constrained); one contract PDF per locação; cancel flow reverses both the Asaas subscription and the moto's availability.
- Payment status values are the fixed Asaas set (PENDING, RECEIVED, CONFIRMED, OVERDUE, CANCELED, REFUNDED, CHARGEBACK, RECEIVED_IN_CASH).
- Auth is currently a single hardcoded admin/admin credential — not backed by the `usuarios` table yet; no signup, no roles, no permissions model. Treat as fixed for now unless the user says otherwise.
- Undecided: real login/user model, driver's-license upload flow, and whether the business ever grows past one operator/one location.

## Brand Commitments

Product/brand name going forward is **AluguelFácil** (the repo's name), replacing the placeholder "MotoRental" currently shown in the UI (`templates/base.html` title/navbar, footer). No logo, color, or typography commitments exist yet — visual identity is undecided and belongs to future design work, not this file.

## Evidence on Hand

No real customer/fleet data, logo, or contract-copy assets were found in the repo. Uploaded contracts, license docs, and moto photos are user-generated at runtime, not sample content to design from. Future design work should not fabricate testimonials, pricing, or sample business data.

## Product Principles

1. Single source of truth: the app should stay the operator's one place to check client, fleet, and billing state — not a thin wrapper the owner still cross-checks in Asaas.
2. Money state must always be legible: pagamento_status and boleto history are load-bearing, not decorative — never bury or reformat them away.
3. Fleet availability is a hard constraint: a moto's `disponivel` flag gates what can be rented, and rental creation/cancellation must keep it consistent.
4. Solo-operator scale: design for one person moving fast through repetitive daily tasks (cadastrar, abrir locação, checar boleto), not for team hand-offs or approval chains.
5. Portuguese-first, Brazilian back-office conventions (CPF, boleto, pt-BR dates/currency) are the default frame, not an afterthought localization.
