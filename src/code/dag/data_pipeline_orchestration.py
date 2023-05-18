from datetime import datetime, timedelta
from airflow import DAG
from airflow.models.baseoperator import chain
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.operators.glue_crawler import GlueCrawlerOperator
from airflow.providers.amazon.aws.operators.s3 import S3DeleteObjectsOperator

import os

DAG_ID=os.path.basename(__file__).replace(".py", "")

DEFAULT_ARGS={
            # the number of retries that should be performed before failing the task
            "owner": "Nahmad",
            "retries": 1,
            "email_on_failure": False,
            "email_on_retry": False,
        }
job_name = "cars-data-transformation"
region_name= "us-east-1"
iam_role_name="demo-mwaa-glue"

config = {
    "Name":"catalog-cars-data",
    "Role": "demo-mwaa-glue",
    "DatabaseName":"curated-data",
    "Description":"Crawl cars dataset and catalog the the data",
    'Targets':{'S3Targets' : [{'Path': "s3://airflowmwaa-demo/curated-data/" }]}
}

with DAG(
        dag_id= DAG_ID,   
        description='Prepare data pipeline orchestration demo',
        default_args = DEFAULT_ARGS,
        start_date=datetime(2023, 4, 28),
        schedule_interval=None,
        dagrun_timeout=timedelta(minutes=10),
        catchup=False,
        tags=["Data Pipeline Orchestration"]
) as dag:
    begin = DummyOperator(task_id="begin")

    end = DummyOperator(task_id="end")
    
    purge_processed_data_s3_objects = BashOperator(
        task_id="purge_processed_data_s3_objects",
        bash_command=f'aws s3 rm s3://airflowmwaa-demo/processed-data/ --recursive',
    )
        
    purge_data_catalog = BashOperator(
        task_id="purge_data_catalog",
        bash_command='aws glue delete-table --database-name curated-data --name curated_data || echo "Database cars-details not found."',
    )
    
    run_glue_job = GlueJobOperator(
        task_id="run_glue_job",
        job_name=job_name,
        region_name= region_name,
        script_location="s3://airflowmwaa-demo/scripts/etlscript.py",
        s3_bucket="airflowmwaa-demo",
        iam_role_name=iam_role_name,
        aws_conn_id="aws_default",
        create_job_kwargs={"GlueVersion": "3.0",
                           "WorkerType": "G.1X",
                           "NumberOfWorkers": 4,},      
    )
    
    run_glue_crawler = GlueCrawlerOperator(
        task_id="run_glue_crawler",
        aws_conn_id= "aws_default",
        config=config,       
    )
    
    sync_buckets = BashOperator(
        task_id="sync_buckets",
        bash_command='aws s3 sync s3://airflowmwaa-demo/landed-zone/  s3://airflowmwaa-demo/processed-data/',
    )
    
    purge_raw_data_file = S3DeleteObjectsOperator(
        task_id="purge_raw_data_file",
        bucket="airflowmwaa-demo",
        keys=["landed-zone/carsdetail.csv"],
        aws_conn_id="aws_default",
    ) 
    
chain(
    begin,
    (purge_processed_data_s3_objects,purge_data_catalog),
    (run_glue_job),
    (run_glue_crawler),
    (sync_buckets),
    (purge_raw_data_file),
    end
)