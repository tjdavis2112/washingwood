// Every page the site builds from the example fixture, for tests that cover all pages.
export const NAV = ["Home", "Seasons", "Owners", "Matchups", "Record Book", "Hall of Fame", "Draft", "Transactions", "League Rules"];

export const COMING_SOON: Record<string, string> = {
  "/hall-of-fame/": "Hall of Fame",
  "/league-rules/": "League Rules",
};

// contract/examples has Seasons 2018 and 2020, and Wren Solano is its former Owner
export const ALL_PAGES = [
  "/",
  "/seasons/",
  "/seasons/2018/",
  "/seasons/2020/",
  "/owners/",
  "/owners/quinn-harrow/",
  "/owners/wren-solano/",
  "/draft/",
  "/matchups/",
  "/record-book/",
  "/transactions/",
  "/matchups/abel-trice-vs-cass-imber/",
  "/matchups/2018/1/quinn-harrow-vs-wren-solano/",
  "/matchups/2018/14/quinn-harrow-vs-wren-solano/",
  ...Object.keys(COMING_SOON),
];
