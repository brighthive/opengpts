from langchain.tools import BaseTool
import requests
from pydantic import BaseModel, Field
from typing import List
import os

ADEPT_ID_API_KEY = os.getenv("ADEPTID_API_KEY")

# Define the input schema for the tool
class WorkHistory(BaseModel):
    title: str
    start_date: str
    end_date: str

class Education(BaseModel):
    level: str
    degree_type: str
    subject: str
    start_date: str
    end_date: str
    institution: str
    gpa: float
    summary: str

class Candidate(BaseModel):
    id: str
    work_history: List[WorkHistory]
    education: List[Education]
    skills: List[str]

class AdeptIDSkillSearchInput(BaseModel):
    skills: List[str]
    result_count: int = 1
    offset: int = 1

class AdeptIDDestionationOccupationRecommendationInput(BaseModel):
    candidates: List[Candidate]
    limit: int = 10
    offset: int = 1

class AdeptIDJobRecommendationInput(BaseModel):
    skill_count: int = 0
    destination_jobs: List[str]
    limit: int = 1000
    offset: int = 0

class AdeptIDSkillSearch(BaseTool):
    name = "AdeptIDSkillSearch"
    description = "Searches for skills and returns the top results."

    input = AdeptIDSkillSearchInput

    def _run(self, input: AdeptIDSkillSearchInput):
        url = "https://api.adept-id.com/v2/skill"
        api_key = os.getenv("ADEPTID_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"  # Replace with your actual API key
        }
        payload = input.json()
        #TODO: check whether this is GET or POST
        response = requests.post(url, headers=headers, data=payload)

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": response.json()}

class AdeptIDDestinationOccupationRecommendation(BaseTool):
    name = "AdeptIDDestinationOccupationRecommendation"
    description = "Recommends occupations and career paths to a candidate based on their skills and interests."

    input = AdeptIDDestionationOccupationRecommendationInput

    def _run(self, input: AdeptIDJobRecommendationInput):
        url = "https://api.adept-id.com/v2/recommend-destination-occupation"
        api_key = os.getenv("ADEPTID_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"  # Replace with your actual API key
        }
        payload = input.json()

        response = requests.post(url, headers=headers, data=payload)

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": response.json()}

# Define the tool class
class AdeptIDJobRecommendation(BaseTool):
    name = "AdeptIDJobRecommendation"
    description = "Recommends specific jobs for a candidate based on their destination occupation and skills."

    input = AdeptIDJobRecommendationInput

    def _run(self, input: AdeptIDJobRecommendationInput):
        url = "https://api.adept-id.com/v2/evaluate-jobs"
        api_key = os.getenv("ADEPTID_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"  # Replace with your actual API key
        }
        payload = input.json()

        response = requests.post(url, headers=headers, data=payload)

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": response.json()}

# Example usage
if __name__ == "__main__":
    tool = AdeptIDJobRecommendation()
    
    # Example input
    input_data = AdeptIDJobRecommendationInput(
        candidates=[
            Candidate(
                id="Piya Gupta",
                work_history=[
                    WorkHistory(title="Retail Sales Associate", start_date="12/2019", end_date="4/2022"),
                    WorkHistory(title="Graphic Designer", start_date="5/2022", end_date="4/2024")
                ],
                education=[
                    Education(
                        level="ASSOCIATES", degree_type="ASSOCIATE OF ARTS", subject="Business",
                        start_date="09/2020", end_date="06/2022",
                        institution="Northern Virgina Community College", gpa=3.5,
                        summary="Completed Associate's in Business with a concentration in marketing and high honors graduation"
                    )
                ],
                skills=["Graphic Design", "Adobe Photoshop", "Illustration", "Marketing", "Logo Design", "Merchandising", "Writing"]
            )
        ],
        limit=10,
        offset=1,
        skill_count=5
    )


    result = tool.run(input_data)
    print(result)
