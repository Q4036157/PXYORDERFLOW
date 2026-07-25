# Contributing

Thanks for helping improve PXYORDERFLOW.

## Development workflow

1. Create a focused branch from `main`.
2. Keep exchange-specific credentials and private endpoints out of the branch.
3. Run the backend tests and frontend type check/build.
4. Open a pull request describing behavior, risks, and verification.

```powershell
python -m unittest discover -s tests -v
cd frontend
npm ci
npm run typecheck
npm run build
```

Changes to order placement, cancellation, authentication, tenant isolation, or
risk limits require tests that cover unauthorized and failure paths.

Good first contributions include documentation, deterministic fixtures,
visualization improvements, replay tooling, and Mock-backed adapter tests.
