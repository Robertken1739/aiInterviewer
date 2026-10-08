Base idea : 
    Metadata :
        User+His base data (Assume resume+data extract) is the metadata/base info (Not required for MVP)
        Job description is what kinda person we're looking for (Not required for mvp)
    Helper LLM : 
        Helper LLM is just an agentic search loop with a dumb AI model with a base prompt explaining how much info we are allowed to share to the user (Can we give the direct ans? Or only hints?)
        Use Langggraph for simplicity of modification later. Manual loop also ok. Use a readymade open souce vector DB to embed and index each of the information paragraph.

        Fetch some K results when user asks a question Show btoh the ai description of what it found and the raw data to the user.

    Smart LLM :
        (Main working mentioned in the loop outline section)
        We need a smart context management system to save tokens. (Worst case summarize with a dumber model if window gets too big) 
            We need to provide user data, Job description data etc once we're out of the MVP phase

    Loop outline :
        User opens a session
        Smart LLM chooses a question
        User prepares by askin dumb LLM/Helper LLM for hints
        Users starts answering/Confrims he's ready to ans
        "Ability to ask helper LLM questions" gets disabled
        User answers 
        Give smart LLM context on the situation and allow it to score the user. (Give some previous examples of scoring so scoring isnt super random). 
        Allow smart LLM to ask followups for final scoring etc
        Scoring system might need tuning based on the requirements
    Maintain sessions on server side for each user
        Which question is user on? 
        How/what did user perform like on previous questions, what were they etc
        User wont be able to use helper AI once he starts answering questions
