Skip To Main Content
statsperform.com
About
News
Contact

Contents
American Football
Australian Football
Badminton
Baseball
Basketball
Beach Soccer
Cricket
Futsal
Golf
Handball
Ice Hockey
Motorsports
Rugby League
Rugby Union
Soccer
Soccer Coverage Tiers
Opta Sports Data Soccer API Legacy IDs
Tournament Schedule (MA0)
Fixtures And Results (MA1)
Fixtures And Results (MA1_Detailed)
Match Stats (MA2)
Match Events (MA3)
Pass Matrix And Average Formation (MA4)
Possession (MA5)
Commentary (MA6)
Match Preview (MA8)
Match Facts (MA9)
Match Expected Goals (MA12)
Possession Events (MA13)
Match Facts Betting (MA15)
Match Facts All (MA16)
Match Stats Points (MA17)
Match Penalties Preview (MA19)
Match Player Ratings (MA20)
Live Win Probability (MA21)
NLG Match Preview (MA22)
Automated Insights (MA23)
Match Fitness (MA24)
Match Tracking (MA25)
NLG Match Recap (MA26)
Match Momentum (MA27)
Match Possession Value (MA30)
TV Listing (MA31)
Match Events Possession Value (MA32)
In-Venue Shape (MA33)
Remote Shape (MA34)
Remote Enriched Events (MA35)
In-Venue Enriched Event (MA36)
Remote Aggregated Events Feed (MA39)
In-Venue Aggregated Events (MA40)
Remote Pressure Timelines (MA41)
In-Venue Pressure Timelines (MA42)
Match Playtime (MA43)
Remote Aggregated Fitness (MA44)
In-Venue Aggregated Fitness (MA45)
Match Provisional LineUps (MA46)
Match Corners Preview (MA47)
Remote Match Tracking EPTS (MA49)
Manager Preview (MA50)
In-Venue Player Shape (MA51)
Remote Player Shape (MA52)
Match Stream (MA53)
In-Venue Aggregated Runs (MA54)
Remote Aggregated Runs (MA55)
In-Venue Aggregated Phases (MA56)
Remote Aggregared Phases (MA57)
In-Venue Player Runs (MA58)
Remote Player Runs (MA59)
In-Venue Phases Of Play (MA60)
Remote Phases Of Play (MA61)
Match Weather Forecast (MA62)
Mappings (MAP)
Match Reference (MAR)
Decode (DEC)
Deletions (DEL)
Tournament Calendars (OT2)
Venues (OT3)
Areas (OT4)
Player Career (PE2)
Referees (PE3)
Rankings (PE4)
Top Performers (PE6)
Injuries (PE7)
Suspensions (PE8)
NLG Dynamic Player Bios (PE9)
Player Possession Value (PE10)
Player Contract (PE12)
Referee Stats Feed (PE13)
Season Points Rankings (PE14)
Person Reference (PER)
Insights (TDM1)
Aggregates (TDM2)
Tournament Calendar Reference (TMR)
Teams (TM1)
Team Standings (TM2)
Squads (TM3)
Seasonal Stats (TM4)
Transfers (TM7)
Trophies (TM8)
Season Expected Goals (TM9)
Season Player Ratings (TM10)
Tournament Simulations (TM11)
Season Simulations (TM12)
Season Power Rankings (TM14)
Team Player Predictions (TM15)
Contestant Participation (TM16)
Season Playtime (TM17)
Season And Tournament Simulations (TM18)
Other Rankings (TM19)
Tennis
Volleyball
Swagger
FAQs & Guides
Shared Resources



Home:
Soccer API Index and User Guide


Last modified on


Sports Data Soccer API Index and User Guide
Our APIs provide external applications access to assets and data stored in Opta and Perform platforms.

Through Sports Data Perform Feeds your applications can retrieve sports data about Soccer squads, competitions, scheduling information from tournament calendars, and individual fixtures. Each API is based on REST principles: you can access data via standard GET requests over HTTPS in UTF-8 format to an API endpoint, and add query parameters to search and control the results in the feed.

Required Compliance:
To comply with our API security and best practice logic for your API calls please refer to our FAQs. We also recommend that you take a look at our API Overview and Authentication Guide. You will learn the basics of how our API works and key concepts to get started.
Base domain: You should use the standard base domain to access our Sports Data API service, unless we have advised you otherwise or if your IP address or domain is in China.
Chinese domains or IP addresses: If your IP address or domain is in China, you should replace the base domain with the following: api.statsperform-hosted.com.cn (effective from 9 September 2020)
Soccer API - Overview
You can get data from the following feeds of the Soccer API. Access to these feeds is subject to your current level of subscription.

To get started, find your feed(s) in the table and visit the dedicated section. You will see a user guide for the feed, use cases, and supported query parameters to help you to customise your requests and get the assets and metadata you require. You can combine multiple query parameter-value strings in one URL to make a single HTTP GET request.
This example is for a standard GET request but it is possible to make requests using OAuth. For more information about the available security and authorisation options including OAuth, see our API Overview and Authorisation Guide. For a tutorial on how to make OAuth requests, see our FAQ: How can I make requests using OAuth?

Base URL and structure:

The examples in our guides use HTTP format. URL requests broadly use the following structure. In the Soccer API, the feedResource is soccerdata.

Get/search assets

GET {protocol}://{requestDomain}/{feedResource}/{feedName}/{outletAuthKey}?{queryParameters}
Get/search an individual asset by UUID

GET {protocol}://{requestDomain}/{feedResource}/{feedName}/{outletAuthKey}/{assetId}?{queryParameters}
Element	Definition
{protocol}	https is the default request type
{requestDomain}	Request domain to access the Sports Data API. For most clients, this is the default: api.performfeeds.com
Use the default unless a custom domain has been supplied by your account manager.
{feedResource}	Resource of the Sports Data API. In this case, the Soccer API: soccerdata
{feedName}	Feed name of the resource, in the case of the Soccer API. For example: standings
{outletAuthKey}	Outlet Authentication Key. A unique 26-character alphanumeric UUID which is unique to each outlet. Any requests made without a valid authentication key will be rejected. This is supplied in the account activation information and access URL.
{queryParameters}	Query parameters. There are required and optional parameters. Optional parameters can help you to search the feed and control the returned content, formatting, and page size. Global query parameters can be used in most feeds, but some query parameters can only be used in certain feeds. The guide for each feed provides the supported parameters and example queries. See Using Query Parameters in our Global Parameters guide.
Note: To keep these feed URLs concise, we have omitted the placeholder {queryParameters} and base URL: {protocol}://{requestDomain}/{feedResource}
In our guides, we use HTTPS syntax for our example GET requests (rather than cURL, for example). All URLs are case-sensitive - this means that URL strings must contain the correct case and operators. You MUST format your requests correctly and include certain information; otherwise, an error will be returned. You can find further information about the API in the API Overview and Authorisation guide.
Include the following information in the URL or header and make sure it is correct for your outlet: your unique and valid {outletAuthKey} this must be after the Outlet Authentication Key (and endpoint, if applicable). for _rt={mode} (operating mode) and _fmt={dataFormat} (response format). If the feed/call requires it, it should also include an entity UUID.
Begin the query parameter string with ? (question mark) - this must be after the Outlet Authentication Key (and endpoint, if applicable). To build up a query string, make sure that each query parameter is separated by the & (ampersand) operator. Values must be separated by the correct operator, for example & (multiple values, 'AND'), or - if a parameter supports it - , (multiple values, 'OR') or ! ('NOT').
Use the required _ (underscore) for any parameters listed with this prefix.
Remove any placeholder value curly braces {} from your calls (we include these as an example only).
If using the JSONP format (_fmt=jsonp) you MUST use it in combination with the callback parameter (_clbk) and a fixed value (or where you use a different value in a different instance, you must do this as little as possible). Be aware that common JavaScript frameworks, such as jQuery, can default to use randomly-generated function names - you must make sure that these are overridden and define a fixed function name instead.
We have introduced the Swagger interactive tool, which enables you to explore, test, and validate API endpoints effortlessly. It provides a user-friendly interface to send requests and view responses, making API testing easier without requiring external tools.

Access the Swagger interface here
Soccer API - Available Feeds
Click next to a feed name to show (or hide) a summary about what the feed offers.

Feed	Endpoint	Reference
Tournament Schedule Feed (MA0)	/soccerdata/tournamentschedule/{outletAuthKey}	User Guide
Fixtures and Results Feed (MA1)	/soccerdata/match/{outletAuthKey}	User Guide
Fixtures and Results Feed (MA1_detailed)	/soccerdata/matchdetailed/{outletAuthKey}	User Guide
Match Stats Feed (MA2)	/soccerdata/matchstats/{outletAuthKey}	User Guide
Match Events Feed (MA3)	/soccerdata/matchevent/{outletAuthKey}	User Guide
Pass Matrix and Average Formation Feed (MA4)	/soccerdata/passmatrix/{outletAuthKey}	User Guide
Possession Feed (MA5)	/soccerdata/possession/{outletAuthKey}	User Guide
Commentary Feed (MA6)	/soccerdata/commentary/{outletAuthKey}	User Guide
Match Preview Feed  (MA8)	/soccerdata/matchpreview/{outletAuthKey}	User Guide
Match Facts Feed (MA9)	/soccerdata/matchfacts/{outletAuthKey}	User Guide
Match Expected Goals Feed (MA12)	/soccerdata/matchexpectedgoals/{outletAuthKey}	User Guide
Possession Events Feed (MA13)	/soccerdata/possessionevent/{outletAuthKey}	User Guide
Match Facts Betting Feed (MA15)	/soccerdata/matchfactsbetting/{outletAuthKey}	User Guide
Match Facts - All Feed (MA16)	/soccerdata/matchfactsall/{outletAuthKey}	User Guide
Match Points Feed (MA17)	/soccerdata/matchstatspoints/{outletAuthKey}	User Guide
Match Penalties Preview Feed (MA19)	/soccerdata/matchpenaltiespreview/{outletAuthKey}	User Guide
Match Player Ratings Feed (MA20)	/soccerdata/matchplayerratings/{outletAuthKey}	User Guide
Live Win Probability Feed (MA21)	/soccerdata/matchlivewinprobability/{outletAuthKey}	User Guide
NLG Match Preview Feed (MA22)	/soccerdata/nlgmatchpreview/{outletAuthKey}	User Guide
Automated Insights Feed (MA23)	/soccerdata/matchinsights/{outletAuthKey}	User Guide
Match Fitness Feed (MA24)	/soccerdata/matchfitness/{outletAuthKey}	User Guide
Match Tracking Feed (MA25)	/soccerdata/matchtracking/{outletAuthKey}	User Guide
NLG Match Recap Feed (MA26)	/soccerdata/nlgmatchrecap/{outletAuthKey}	User Guide
Match Momentum Feed (MA27)	/soccerdata/predictions/momentum/{outletAuthKey}	User Guide
Match Possession Value Feed (MA30)	/soccerdata/matchpossessionvalues/{outletAuthKey}	User Guide
TV Listing Feed (MA31)	/soccerdata/matchtvlisting/{outletAuthKey}	User Guide
Match Events Possession Value Feed (MA32)	/soccerdata/matcheventspossessionvalues
/{outletAuthKey}	User Guide
In-Venue Shape Feed (MA33)	/soccerdata/invenueshape/{outletAuthKey}	User Guide
Remote Shape Feed (MA34)	/soccerdata/remoteshape/{outletAuthKey}	User Guide
Remote Enriched Soccer Events Feed (MA35)	/soccerdata/remoteevents/{outletAuthKey}	User Guide
In-venue Enriched Soccer Events Feed (MA36)	/soccerdata/invenueevents/{outletAuthKey}	User Guide
Remote Aggregated Events Feed (MA39)	/soccerdata/remoteaggregatedevents/{outletAuthKey}	User Guide
In-Venue Aggregated Events Feed (MA40)	/soccerdata/invenueaggregatedevents/{outletAuthKey}	User Guide
Remote Pressure Timelines Feed (MA41)	/soccerdata/remotepressuretimeline/{outletAuthKey}	User Guide
In-Venue Pressure Timelines Feed (MA42)	/soccerdata/invenuepressuretimeline/{outletAuthKey}	User Guide
Match Playtime Feed (MA43)	/soccerdata/matchplaytime/{outletAuthKey}	User Guide
Remote Aggregated Fitness Feed (MA44)	/soccerdata/remoteaggregatedfitness/{outletAuthKey}	User Guide
In Venue Aggregated Fitness Feed (MA45)	/soccerdata/invenueaggregatedfitness/{outletAuthKey}	User Guide
Match Provisional LineUps Feed (MA46)	/soccerdata/matchProvisionalLineUps/{outletAuthKey}	User Guide
Match Corners Preview Feed (MA47)	/soccerdata/matchcornerspreview/{outletAuthKey}	User Guide
Remote Match Tracking EPTS Feed (MA49)	/soccerdata/remotematchtrackingepts/{outletAuthKey}	User Guide
Manager Preview Feed (MA50)	/soccerdata/managerpreview/{outletAuthKey}	User Guide
In-Venue Player Shape Feed (MA51)	/soccerdata/inVenuePlayerShape/{outletAuthKey}	User Guide
Remote Player Shape Feed (MA52)	/soccerdata/remoteplayershape/{outletAuthKey}	User Guide
Match Stream Feed (MA53)	/soccerdata/matchstream/{outletAuthKey}	User Guide
In-Venue Aggregated Runs Feed (MA54)	/soccerdata/invenueaggregatedruns/{outletAuthKey}	User Guide
Remote Aggregated Runs Feed (MA55)	/soccerdata/remoteaggregatedruns/{outletAuthKey}	User Guide
In-venue Aggregated Phases Feed (MA56)	/soccerdata/invenueaggregatedphases/{outletAuthKey}	User Guide
Remote Aggregated Phases Feed (MA57)	/soccerdata/remoteaggregatedphases/{outletAuthKey}	User Guide
In-venue Player Runs Feed (MA58)	/soccerdata/invenueplayerruns/{outletAuthKey}	User Guide
Remote Player Runs Feed (MA59)	/soccerdata/remoteplayerruns/{outletAuthKey}	User Guide
In Venue Phases of Play (MA60)	/soccerdata/invenuephasesofplay/{outletAuthKey}	User Guide
Remote Phases of Play (MA61)	/soccerdata/remotephasesofplay/{outletAuthKey}	User Guide
Match Weather Forecast (MA62)	/soccerdata/weatherforecasts/{outletAuthKey}	User Guide
Mappings Feed (MAP)	/soccerdata/mappings/{outletAuthKey}	User Guide
Match Reference Feed (MAR)	/soccerdata/matchreference/{outletAuthKey}	User Guide
Deletions Feed (DEL)	/soccerdata/deletions/{outletAuthKey}	User Guide
Decode Feed (DEC)	/soccerdata/decode/{outletAuthKey}	User Guide
Tournament Calendars Feed (OT2)	/soccerdata/tournamentcalendar/{outletAuthKey}	User Guide
Venues Feed (OT3)	/soccerdata/venues/{outletAuthKey}	User Guide
Areas Feed (OT4)	/soccerdata/areas/{outletAuthKey}	User Guide
Player Career Feed (PE2)	/soccerdata/playercareer/{outletAuthKey}	User Guide
Referees Feed (PE3)	/soccerdata/referees/{outletAuthKey}	User Guide
Rankings Feed (PE4)	/soccerdata/rankings/{outletAuthKey}	User Guide
Top Performers Feed (PE6)	/soccerdata/topperformers/{outletAuthKey}	User Guide
Injuries Feed (PE7)	/soccerdata/injuries/{outletAuthKey}	User Guide
Suspensions Feed (PE8)	/soccerdata/suspensions/{outletAuthKey}	User Guide
NLG Dynamic Player Bios Feed (PE9)	/soccerdata/nlgdynamicplayerbio/{outletAuthKey}	User Guide
Player Possession Feed (PE10)	/soccerdata/playerpossessionvalues/{outletAuthKey}	User Guide
Player Contract Feed (PE12)	/soccerdata/playercontract/{outletAuthKey}	User Guide
Referee Stats Feed (PE13)	/soccerdata/refereestats/{outletAuthKey}	User Guide
Season Points Rankings Feed (PE14)	/soccerdata/seasonstatspoints/{outletAuthKey}	User Guide
Person Reference Feed (PER)	/soccerdata/personreference/{outletAuthKey}	User Guide
Insights Feed (TDM1)	/soccerdata/tdm/insights/{outletAuthKey}	User Guide
Tournament Calendar Reference Feed (TMR)	/soccerdata/tournamentcalendarreference/{outletAuthKey}	User Guide
Aggregates Feed (TDM2)	/soccerdata/tdm/aggregates/{outletAuthKey}	User Guide
Teams Feed (TM1)	/soccerdata/team/{outletAuthKey}	User Guide
Team Standings Feed (TM2)	/soccerdata/standings/{outletAuthKey}	User Guide
Squads Feed (TM3)	/soccerdata/squads/{outletAuthKey}	User Guide
Seasonal Stats Feed (TM4)	/soccerdata/seasonstats/{outletAuthKey}	User Guide
Transfers Feed (TM7)	/soccerdata/transfers/{outletAuthKey}	User Guide
Trophies Feed (TM8)	/soccerdata/trophies/{outletAuthKey}	User Guide
Season Expected Goals Feed (TM9)	/soccerdata/seasonexpectedgoals/{outletAuthKey}	User Guide
Season Player Ratings Feed (TM10)	/soccerdata/seasonplayerratings/{outletAuthKey}	User Guide
Tournament Simulations Feed (TM11)	/soccerdata/predictions/tournamentsimulations
/{outletAuthKey}	User Guide
Season Simulations Feed (TM12)	/soccerdata/predictions/seasonsimulations
/{outletAuthKey}	User Guide
Season Power Rankings Feed (TM14)	/soccerdata/seasonpowerrankings/{outletAuthKey}	User Guide
Team Player Predictions Feed (TM15)	/soccerdata/teamplayerpredictions
/{outletAuthKey}	User Guide
Contestant Participation Feed (TM16)	/soccerdata/contestantparticipation/{outletAuthKey} 	User Guide
Season Playtime Feed (TM17) 	/soccerdata/seasonplaytime/{outletAuthKey}	User Guide
Season And Tournament Simulations Feed (TM18) 	/soccerdata/seasonandtournamentsimulations/
{outletAuthKey}	User Guide
Other Rankings Feed (TM19) 	/soccerdata/otherrankings/{outletAuthKey}	User Guide
                                                                                                     


In this Topic
Required Compliance:
Soccer API - Overview
Soccer API - Available Feeds

Contact Stats Perform • Terms of Use • Privacy Policy • Cookie Policy • © 2024 Stats Perform	 
