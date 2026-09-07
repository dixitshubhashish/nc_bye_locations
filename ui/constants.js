window.APP_CONSTANTS = Object.freeze({
  productName: "Competitive Whitespace Tool",
  brandName: "Birdeye",
  birdeyeLogoUrl: "https://cdn2.birdeye.com/version2/containers/header/birdeye-logo-2025@2x.png",
  birdeyeLogoDarkUrl: "https://cdn2.birdeye.com/version2/containers/header/birdeye-logo-2025@2x.png",
  birdeyeLogoLightUrl: "https://cdn2.birdeye.com/version2/containers/header/birdeye-logo-2025@2x.png",
  birdeyeFaviconUrl: "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRMN8cedT14Ys3ypKhW3VrDD0t2kE9zx5yzNsXv7sj9kg&s",
  reportingEmbedUrl: "https://lookerstudio.google.com/embed/reporting/1f6e8f3c-2c43-4a55-9f4a-8a4b3f9e2d10/page/p_abc123",
  jsonViewerUrl: "https://codebeautify.org/jsonviewer",
  dominosZipFetchLimit: "all",
  dominosStoresPerZipLimit: 1,
  dominosMaxWorkers: 8,
  dominosProvider: "auto",
  dominosOrderType: "Delivery",
  dominosJsonDemoUrl: "https://data-m8.com/downloads/list-of-all-dominos-pizza-locations-in-the-usa-csv-and-json.json",
  dominosBrand: {
    name: "Domino's Pizza",
    slug: "dominos-pizza",
    description: "Domino's Pizza US store locator data.",
    websiteUrl: "https://www.dominos.com/",
    status: "active",
    metaTitle: "Domino's Pizza",
    metaDescription: "Domino's Pizza US store locator mapping.",
    countryOfOrigin: "United States"
  },
  pizzaHutCsvDemoUrl: "https://raw.githubusercontent.com/stiles/locations/main/pizza-hut/data/processed/pizza-hut_locations.csv",
  pizzaHutBrand: {
    name: "Pizza Hut",
    slug: "pizza-hut",
    description: "Pizza Hut US locations from public processed CSV data.",
    websiteUrl: "https://www.pizzahut.com/",
    status: "active",
    metaTitle: "Pizza Hut",
    metaDescription: "Pizza Hut US locations CSV mapping.",
    countryOfOrigin: "United States"
  },
  laCityJsonDemoUrl: "https://data.lacity.org/api/v3/views/29fd-3paw/query.json",
  laCityJsonDemoBrand: {
    name: "LA City Inspection Demo",
    slug: "la-city-inspection-demo",
    description: "Demo brand for LA City restaurant and market inspection JSON data.",
    websiteUrl: "https://data.lacity.org/",
    status: "active",
    metaTitle: "LA City Inspection Demo",
    metaDescription: "Demo mapping for LA City restaurant and market inspection JSON data.",
    countryOfOrigin: "United States"
  },
  littleCaesarsApiDemoUrl: "https://nominatim.openstreetmap.org/search",
  littleCaesarsBrand: {
    name: "Little Caesars",
    slug: "little-caesars",
    description: "Little Caesars US store locations via REST API GET (JSON/XML).",
    websiteUrl: "https://littlecaesars.com/",
    status: "active",
    metaTitle: "Little Caesars",
    metaDescription: "Little Caesars US store locator API mapping.",
    countryOfOrigin: "United States"
  },
  globalHotelsCorruptDemoUrl: "https://raw.githubusercontent.com/Azure-Samples/azure-search-sample-data/main/hotels/HotelsData_toAzureSearch.csv",
  globalHotelsBrand: {
    name: "Global Hospitality & Hotels",
    slug: "global-hospitality-hotels",
    description: "Global hotels dataset with mixed US and non-US entries, malformed ZIP codes, and invalid coordinate edge cases.",
    websiteUrl: "https://azure.microsoft.com/",
    status: "active",
    metaTitle: "Global Hospitality Demo",
    metaDescription: "Demo dataset for testing malformed ZIP codes, out-of-bounds coordinates, and non-US location filtering.",
    countryOfOrigin: "Global"
  },
  demoRestaurantExcelUrl: "https://docs.google.com/spreadsheets/d/e/2PACX-1vSHa0iIxTVG7odLSlxL8PKDdAt0Xo2ciufPLMpGm9pQuOi44nlwgs3N-Dew4pyz7g/pub?output=xlsx",
  demoXmlUrl: "https://samplelib.com/xml/sample-5mb.xml",
  demoXmlBrand: {
    name: "Demo XML",
    slug: "demo-xml",
    description: "Public XML structure and nested-record parsing demo.",
    websiteUrl: "https://github.com/MichielCM/xsd2html2xml",
    status: "active",
    metaTitle: "Demo XML",
    metaDescription: "Demo XML source for parser and nested field mapping validation.",
    countryOfOrigin: "United States"
  },
  trademarkDisclaimer: "Birdeye is a trademark of Birdeye, Inc. All rights in the Birdeye name and logo are reserved by Birdeye, Inc. This prototype uses the provided brand asset for reference and is not affiliated with, sponsored by, or endorsed by Birdeye. This prototype is provided for assessment and evaluation purposes only; no other use is intended or authorized."
});

// Add exactly two internal tabs inside the existing Reporting screen:
// Location Intelligence & Whitespace, and Data Quality & Improvements.
(() => {
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-product-name]").forEach((element) => {
      element.textContent = window.APP_CONSTANTS.productName;
    });
  });
  const script = document.createElement("script");
  script.src = "/reporting-tabs.js";
  script.async = true;
  document.head.appendChild(script);
})();
