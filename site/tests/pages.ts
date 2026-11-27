// Every page the site builds from the example fixture, for tests that cover all pages.
export const NAV = ["Home", "Seasons", "Owners", "Matchups", "Record Book", "Hall of Fame", "Draft", "Transactions", "League Rules"];

export const COMING_SOON: Record<string, string> = {
  "/owners/": "Owners",
  "/matchups/": "Matchups",
  "/record-book/": "Record Book",
  "/hall-of-fame/": "Hall of Fame",
  "/draft/": "Draft",
  "/transactions/": "Transactions",
  "/league-rules/": "League Rules",
};

// contract/examples has Seasons 2018 and 2020
export const ALL_PAGES = ["/", "/seasons/", "/seasons/2018/", "/seasons/2020/", ...Object.keys(COMING_SOON)];
