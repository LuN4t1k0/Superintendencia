const fs = require("fs");
const path = require("path");

const outputPath = path.resolve(__dirname, "..", "src", "config.generated.json");
const config = {
  appId: process.env.APP_ID || "afp-lookup",
  licenseServerUrl: process.env.LICENSE_SERVER_URL || "",
  licenseOfflineGraceDays: Number(process.env.LICENSE_OFFLINE_GRACE_DAYS || "7")
};

fs.writeFileSync(outputPath, `${JSON.stringify(config, null, 2)}\n`);
console.log(`Config generada: ${outputPath}`);
