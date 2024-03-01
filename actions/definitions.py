"""
Store definitions used in rasa actions (e.g., related to database).
"""

import pandas as pd

DATABASE_HOST = "mysql"
DATABASE_PASSWORD = "treelisbonmaijanuar445599!!!!!22333"
DATABASE_PORT = 3306
DATABASE_USER = "root"


# List of preparatory activities
df_act = pd.read_excel("Activities.xlsx", 
                       converters={'Exclusion':str, 'Prerequisite':str})
# Turn exclusion and prerequisite columns into lists
df_act["Exclusion"] = [list(df_act.iloc[i]["Exclusion"].split("|")) if not pd.isna(df_act.iloc[i]["Exclusion"]) else [] for i in range(len(df_act))]
# Note: when there are multiple prerequisites, only one needs to be met
df_act["Prerequisite"] = [list(df_act.iloc[i]["Prerequisite"].split("|")) if not pd.isna(df_act.iloc[i]["Prerequisite"]) else [] for i in range(len(df_act))]


# Number of activities
NUM_ACTIVITIES = len(df_act)


# Mininum number of characters for activity experience response
# and the possible modification
MIN_CHAR_EXPERIENCE = 20
MIN_CHAR_EXPERIENCE_MOD = 5


# Minimum number of characters for introduction to human coach
MIN_CHAR_HUMAN_COACH_INTRO = 70


# Probability of receiving human support
PROB_HUMAN_SUPPORT = 0.2
