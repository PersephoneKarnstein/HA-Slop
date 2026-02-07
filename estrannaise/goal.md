I would like you to design and implement a home assistant integration for blood estrogen level monitoring, based on https://estrannai.se . The end goal is to have three cards, plus a number of integration configuration options, and data stored locally in a sqlite database. The cards should be as follows:

MAIN CARD: a plotly graph card, showing the user's estimated blood estrogen level over time, similar to https://estrannai.se/ . The YAML configuration for the card should allow you to display or hide a target range and a menstrual cycle range, and set up recurring doses of estrogen via the major esters and methods (valerate, cypionate, etc. and intramuscular, subcutaneous, patch, pill, etc.). The YAML for adding these should mirror that of setting a standard entity trace in https://github.com/dbuezas/lovelace-plotly-graph-card . Configuration for dosing should be either automatic (recurring doses) or manual (via CARD 2), in which case the user would click CARD 2 == BUTTON 1 every time they take their estrogen. The chart should by default display approximately 1 week into the past, and with a dotted line, one week into the future based on current body estrogen levels.

CARD 2 - BUTTON 1: a button representing manual tracking of estrogen regimen. When clicked, a single dose of estrogen via a set ester and intake method is added to the chart at the time when the button was clicked. This button can be disabled if automatic recurring dosing is enabled; if it is NOT disabled AND recurring doses are enabled, the manual dose should be added to the automatic trace and the estimated blood levels should be recalculated with that addition.

CARD 3 - BUTTON 2: a button that pops up a dialog box giving the user multiple options for inputting the results of blood e2 tests, such as time the tested blood was taken, tested levels, etc. When a blood test is added, the data should be added to the sqlite database and the estimated blood levels displayed on the MAIN CARD should be scaled such that the estimated levels are in line with the measured levels. This scaling factor should be a small multiplicative factor, between 0 and ~2.

the data should all be stored locally in the sqlite database and never touch the network. this is PRIVATE data. The amount of time after which manual dosing data becomes stale and no longer needs to be included in estimates will vary by ester, as they all have different half-lives, but in general should be once the estimated blood level contribution is ~1% of its contribution at peak. This is to prevent extremely old data from slowing down calculation. The user should also have the option to automatically send dosing times to the home assistant calendar. This will be helpful if they are attempting to follow a more complex dosing schedule, such as imitating a cis feminine menstrual cycle.

ask me if you have any implementation questions.


SOURCES:
- https://github.com/WHSAH/estrannaise.js
- https://estrannai.se/
- https://pghrt.diy/
- https://github.com/dbuezas/lovelace-plotly-graph-card
- https://simpy.readthedocs.io/en/latest/ (if necessary)
- pharmacokinetics equations (as necessary)