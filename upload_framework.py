import boto3
import os
import json
import mimetypes
import time
import hashlib
import argparse
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# --- Color Codes for Console Output ---
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'
CYAN = '\033[96m'

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Load Environment Variables ---
load_dotenv()
BUCKET_NAME = os.getenv("BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

def get_s3_objects(bucket):
    """Get a dictionary of objects in the S3 bucket and their ETags."""
    s3_objects = {}
    try:
        s3 = boto3.client("s3", region_name=AWS_REGION)
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket):
            if 'Contents' in page:
                for obj in page['Contents']:
                    s3_objects[obj['Key']] = obj['ETag'].strip('"')
    except ClientError as e:
        print(f"Error listing bucket objects: {e}")
    return s3_objects

def calculate_local_md5(file_path):
    """Calculate the MD5 hash of a local file."""
    with open(file_path, 'rb') as f:
        md5 = hashlib.md5()
        while chunk := f.read(8192):
            md5.update(chunk)
    return md5.hexdigest()

def find_distribution_id_for_bucket(bucket_name):
    """Find the CloudFront distribution ID associated with an S3 bucket."""
    try:
        cloudfront = boto3.client("cloudfront")
        distributions = cloudfront.list_distributions()
        for dist in distributions.get('DistributionList', {}).get('Items', []):
            for origin in dist.get('Origins', {}).get('Items', []):
                if bucket_name in origin.get('DomainName', ''):
                    return dist['Id']
    except ClientError as e:
        print(f"Error finding distribution: {e}")
    return None

def invalidate_cloudfront_cache(distribution_id, items):
    """Create a CloudFront invalidation for the specified items."""
    if not distribution_id:
        print("Could not find a distribution ID to invalidate.")
        return
    if not items:
        print("No files to invalidate.")
        return
        
    print(f"Creating invalidation for {len(items)} files in distribution: {distribution_id}")
    try:
        cloudfront = boto3.client("cloudfront")
        cloudfront.create_invalidation(
            DistributionId=distribution_id,
            InvalidationBatch={
                'Paths': {
                    'Quantity': len(items),
                    'Items': [f'/{item}' for item in items] # Paths must start with a '/'
                },
                'CallerReference': f'invalidation-{time.time()}'
            }
        )
        print("Invalidation created successfully.")
    except ClientError as e:
        print(f"Error creating invalidation: {e}")

def main():
    """
    Uploads website framework files to the S3 bucket, skipping unchanged files.
    Accepts command-line arguments for manifest path and source directory.
    """
    parser = argparse.ArgumentParser(description="Uploads website framework files to S3 and invalidates CloudFront cache.")
    parser.add_argument(
        '--manifest-path',
        default=os.path.join(SCRIPT_DIR,"sync_manifest.txt"),
        help='Path to the manifest file listing files to sync. Defaults to sync_manifest.txt in the script directory.'
    )
    parser.add_argument(
        '--source-dir',
        default=os.path.join(SCRIPT_DIR,"localhost"),
        help='Path to the source directory containing the files. Defaults to localhost in the script directory.'
    )
    args = parser.parse_args()

    print("--- Starting Website Framework Upload ---")
    
    manifest_path = os.path.abspath(args.manifest_path)
    source_dir = os.path.abspath(args.source_dir)

    try:
        with open(manifest_path, 'r') as f:
            files_to_sync = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"{YELLOW}Error: Manifest file not found at {manifest_path}{RESET}")
        return

    print(f"Found {len(files_to_sync)} files to sync from manifest: {manifest_path}")
    print(f"Using source directory: {source_dir}")
    
    s3 = boto3.client("s3", region_name=AWS_REGION)
    s3_objects = get_s3_objects(BUCKET_NAME)
    uploaded_files = []

    for file_key in files_to_sync:
        local_path = os.path.join(source_dir, file_key)
        
        if not os.path.exists(local_path):
            print(f"{YELLOW}Warning: File '{local_path}' not found, skipping.{RESET}")
            continue

        local_md5 = calculate_local_md5(local_path)
        remote_etag = s3_objects.get(file_key)

        if local_md5 == remote_etag:
            print(f"{CYAN}Skipping '{file_key}' (unchanged).{RESET}")
            continue

        content_type, _ = mimetypes.guess_type(local_path)
        if content_type is None:
            content_type = 'application/octet-stream'
            
        try:
            s3.upload_file(
                local_path,
                BUCKET_NAME,
                file_key,
                ExtraArgs={'ContentType': content_type}
            )
            print(f"{GREEN}Uploading '{file_key}' (changed)...{RESET}")
            uploaded_files.append(file_key)
        except ClientError as e:
            print(f"Error uploading '{file_key}': {e}")

    # Invalidate the cache for the uploaded files
    if uploaded_files:
        dist_id = find_distribution_id_for_bucket(BUCKET_NAME)
        invalidate_cloudfront_cache(dist_id, uploaded_files)
    else:
        print("No files were uploaded, skipping invalidation.")

    print("--- Framework Upload Complete ---")

if __name__ == "__main__":
    main()