from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import matplotlib.pyplot as plt
import pandas as pd
import io
import pymysql
app = FastAPI()

# Database credentials
DB_HOST = '103.239.89.99'
DB_DATABASE = 'SmartHealAppDB'
DB_USERNAME = 'SmartHealAppUsr'
DB_PASSWORD = 'I^4y1b12y'
DATABASE_URL = f"mysql+pymysql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}/{DB_DATABASE}"

# Create engine and session
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)

db_config = {
    "host": "103.239.89.99",
    "port": 3306,
    "database": "SmartHealAppDB",
    "user": "SmartHealAppUsr",
    "password": "I^4y1b12y"
}


def fetch_data(query: str):
    try:
        connection = pymysql.connect(
            host=db_config["host"],
            port=db_config["port"],
            user=db_config["user"],
            password=db_config["password"],
            database=db_config["database"]
        )
        df = pd.read_sql(query, connection)
        connection.close()
        return df.dropna()
    except pymysql.MySQLError as e:
        raise HTTPException(status_code=500, detail=str(e))

# Helper function to generate image in memory
def generate_image(plt):
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

@app.get("/Type_demographics", summary="shows a bar graph representing different types of wounds present and its count", tags=["Analytics"])
async def get_wound_types():
    try:
        query = "SELECT type, COUNT(*) as count FROM wounds GROUP BY type"
        df = fetch_data(query)
        print(df)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found")

        plt.figure(figsize=(10, 6))
        plt.bar(df['type'], df['count'], color='skyblue')
        plt.xlabel('Wound Type')
        plt.ylabel('Count')
        plt.title('Most Common Wound Types')
        
        buf = generate_image(plt)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/Wound_locations_chart", summary="shows a pie chat representing different wound location", tags=["Analytics"])
async def get_wound_locations():
    try:
        query = "SELECT position, COUNT(*) as count FROM wounds GROUP BY position"
        df = fetch_data(query)
        print(df)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found")
        plt.figure(figsize=(8, 8))
        plt.pie(df['count'], labels=df['position'], autopct='%1.1f%%', startangle=140, colors=plt.cm.Paired.colors)
        plt.title('Wound Location Distribution')
        
        buf = generate_image(plt)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/Tissue_type_demographics", summary="shows a stacked bar graph between wound type and wound tissue", tags=["Analytics"])
async def get_wound_tissue_types():
    try:
        query = """
        SELECT type,
               SUM(CASE WHEN tissue = 'Necrotic' THEN 1 ELSE 0 END) as Necrotic,
               SUM(CASE WHEN tissue = 'Granulating' THEN 1 ELSE 0 END) as Granulating,
               SUM(CASE WHEN tissue = 'Clean' THEN 1 ELSE 0 END) as Clean,
               SUM(CASE WHEN tissue = 'Epithelial' THEN 1 ELSE 0 END) as Epithelial
        FROM wounds
        GROUP BY type
        """
        df = fetch_data(query)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found")

        df.set_index('type', inplace=True)
        df.plot(kind='bar', stacked=True, figsize=(10, 6), colormap='viridis')
        plt.xlabel('Wound Type')
        plt.tick_params(axis='x', labelrotation=0)
        plt.ylabel('Count')
        plt.title('Wound Tissue Type Breakdown')
        plt.legend(title='Tissue Type')
        
        buf = generate_image(plt)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/Wound_size_demographics", summary="shows a bar graph representing average size and depth of the wounds", tags=["Analytics"])
async def get_average_wound_size_depth():
    try:
        query = "SELECT AVG(area) as avg_size, AVG(depth) as avg_depth FROM wounds"
        df = fetch_data(query)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found")

        plt.figure(figsize=(10, 6))
        plt.bar(['Average Size', 'Average Depth'], [df['avg_size'].iloc[0], df['avg_depth'].iloc[0]], color='skyblue')
        plt.ylabel('Average Measurement')
        plt.title('Average Wound Size and Depth')

        buf = generate_image(plt)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/Patients_added", summary="shows line graph representing the number of patients added on a date", tags=["Analytics"])
async def get_total_patients_added():
    try:
        query = "SELECT DATE(created_at) as date, COUNT(*) as count FROM patients GROUP BY DATE(created_at)"
        df = fetch_data(query)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found")

        plt.figure(figsize=(10, 6))
        plt.plot(df['date'], df['count'], marker='o', color='skyblue')
        plt.xlabel('Date')
        plt.ylabel('Number of Patients Added')
        plt.title('Total Number of Patients Added Over Time')

        buf = generate_image(plt)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/age-distribution", summary="shows a histogram displaying the age distripution of the patients", tags=["Analytics"])
async def get_age_distribution():
    try:
        query = "SELECT age FROM patients"
        df = fetch_data(query)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found")

        plt.figure(figsize=(10, 6))
        plt.hist(df['age'], bins=10, color='skyblue', edgecolor='black')
        plt.xlabel('Age')
        plt.ylabel('Count')
        plt.title('Age Distribution of Patients')

        buf = generate_image(plt)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/gender-distribution", summary="shows a pie chart to show the gender distribution of the patients", tags=["Analytics"])
async def get_gender_distribution():
    try:
        query = "SELECT gender, COUNT(*) as count FROM patients GROUP BY gender"
        df = fetch_data(query)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found")

        plt.figure(figsize=(8, 8))
        plt.pie(df['count'], labels=df['gender'], autopct='%1.1f%%', startangle=140, colors=plt.cm.Paired.colors)
        plt.title('Gender Distribution of Patients')

        buf = generate_image(plt)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
