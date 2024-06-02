from langchain.tools import BaseTool
import requests
from pydantic import BaseModel, Field
from typing import List
import os

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

class AdeptIDJobRecommendationInput(BaseModel):
    candidates: List[Candidate]
    limit: int = 10
    offset: int = 1
    skill_count: int = 5

# Define the tool class
class AdeptIDJobRecommendation(BaseTool):
    name = "AdeptIDJobRecommendation"
    description = "Recommends next step career opportunities for a specific candidate."

    input_model = AdeptIDJobRecommendationInput

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
