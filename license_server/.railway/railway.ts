import { defineRailway, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: "us-east4-eqdc4a" });
  Postgres.networking = { privateNetworkEndpoint: "postgres" };
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "us-east4-eqdc4a", sizeMB: 5000 });
  const afpLicenseServer = service("afp-license-server", {
    replicas: { "us-east4-eqdc4a": 1 },
    env: { ADMIN_TOKEN: preserve(), APP_ID: preserve(), DATABASE_URL: preserve(), DEFAULT_APP_ID: preserve(), LICENSE_DB_PATH: preserve() },
  });

  return project("afp-license-server", {
    resources: [afpLicenseServer, Postgres, postgresVolume],
  });
});
