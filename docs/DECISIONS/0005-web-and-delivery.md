# Web and delivery

Strict TypeScript, React, Vite and plain CSS keep the four views small without a component framework. SVG charts use D3 scales/shapes and explicit missing-data gaps. Only two charts exist. Docker images pin immutable base digests and use non-root runtime users. Render configuration uses a free API service, external PostgreSQL and /health; Vercel hosts the static build with an explicit public API origin. Continuous database health polling is avoided so an idle database can scale down. Nothing is deployed by these files alone.
