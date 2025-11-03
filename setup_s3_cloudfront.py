import boto3
import json
import time
import argparse
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv
import os

# --- Load Environment Variables ---
load_dotenv()
BUCKET_NAME = os.getenv("BUCKET_NAME")
DOMAIN_NAME = os.getenv("DOMAIN_NAME")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# --- Boto3 Clients ---
try:
    s3 = boto3.client("s3", region_name=AWS_REGION)
    acm = boto3.client("acm", region_name="us-east-1") # ACM certs for CloudFront must be in us-east-1
    cloudfront = boto3.client("cloudfront")
    route53 = boto3.client("route53")
except NoCredentialsError:
    print("AWS credentials not found. Please configure them.")
    exit()

def create_s3_bucket():
    """Create the S3 bucket if it doesn't exist."""
    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
        print(f"Bucket '{BUCKET_NAME}' already exists.")
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"Creating S3 bucket: {BUCKET_NAME} in region {AWS_REGION}")
            try:
                if AWS_REGION == "us-east-1":
                    s3.create_bucket(Bucket=BUCKET_NAME)
                else:
                    s3.create_bucket(
                        Bucket=BUCKET_NAME,
                        CreateBucketConfiguration={'LocationConstraint': AWS_REGION}
                    )
            except ClientError as err:
                print(f"Error creating bucket: {err}")
                raise
    
    print("Disabling Block Public Access for the bucket...")
    s3.put_public_access_block(
        Bucket=BUCKET_NAME,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': False,
            'IgnorePublicAcls': False,
            'BlockPublicPolicy': False,
            'RestrictPublicBuckets': False
        }
    )
    print("Block Public Access disabled.")

    print("Configuring bucket for static website hosting...")
    s3.put_bucket_website(
        Bucket=BUCKET_NAME,
        WebsiteConfiguration={'IndexDocument': {'Suffix': 'index.html'}}
    )

    print("Applying public read policy to bucket...")
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PublicReadGetObject",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{BUCKET_NAME}/*"
            },
            {
                "Sid": "PublicListBucket",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:ListBucket",
                "Resource": f"arn:aws:s3:::{BUCKET_NAME}"
            }
        ]
    }
    s3.put_bucket_policy(Bucket=BUCKET_NAME, Policy=json.dumps(policy))

    print("Applying CORS configuration to bucket...")
    cors_configuration = {
        'CORSRules': [{
            'AllowedHeaders': ['*'],
            'AllowedMethods': ['GET'],
            'AllowedOrigins': ['*'],
            'ExposeHeaders': [],
            'MaxAgeSeconds': 3000
        }]
    }
    s3.put_bucket_cors(Bucket=BUCKET_NAME, CORSConfiguration=cors_configuration)

    print("Bucket setup complete.")

def get_acm_certificate_arn():
    """Request or find an existing ACM certificate for the DOMAIN_NAME."""
    print(f"Requesting ACM certificate for {DOMAIN_NAME}...")
    paginator = acm.get_paginator('list_certificates')
    for page in paginator.paginate(CertificateStatuses=['ISSUED']):
        for cert in page['CertificateSummaryList']:
            if cert['DomainName'] == DOMAIN_NAME:
                print(f"Found existing certificate: {cert['CertificateArn']}")
                return cert['CertificateArn']
    
    response = acm.request_certificate(
        DomainName=DOMAIN_NAME,
        ValidationMethod='DNS'
    )
    print("Certificate requested. ")
    return response['CertificateArn']

def wait_for_dns_validation_record(cert_arn, timeout=600):
    """Wait up to `timeout` seconds for the DNS validation record to become available."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            cert_details = acm.describe_certificate(CertificateArn=cert_arn)
            validation_options = cert_details['Certificate']['DomainValidationOptions']
            if validation_options and 'ResourceRecord' in validation_options[0]:
                print("DNS validation record found.")
                return validation_options[0]['ResourceRecord']
        except ClientError as e:
            # Handle potential throttling or other errors
            print(f"An error occurred while checking certificate status: {e}")
        
        print("Waiting for DNS validation record to become available...")
        time.sleep(15)
    raise TimeoutError("Timed out waiting for DNS validation record.")

def create_dns_validation_record(cert_arn, zone_id):
    """
    Waits for the DNS validation record to become available and then creates it in Route 53.
    """
    record = wait_for_dns_validation_record(cert_arn)
    
    print(f"Creating DNS validation record: {record['Name']} -> {record['Value']}")

    try:
        route53.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                'Changes': [{
                    'Action': 'UPSERT',
                    'ResourceRecordSet': {
                        'Name': record['Name'],
                        'Type': record['Type'],
                        'TTL': 300,
                        'ResourceRecords': [{'Value': record['Value']}]
                    }
                }]
            }
        )
        print("Validation record created/updated in Route 53.")
    except ClientError as e:
        print(f"Error creating DNS record in Route 53: {e}")
        raise

def wait_for_certificate_issued(cert_arn, timeout=600):
    """Wait up to `timeout` seconds for ACM certificate to be issued."""
    start = time.time()
    while time.time() - start < timeout:
        status = acm.describe_certificate(CertificateArn=cert_arn)['Certificate']['Status']
        print(f"Certificate status: {status}")
        if status == 'ISSUED':
            return True
        elif status == 'FAILED':
            raise RuntimeError("Certificate request failed")
        time.sleep(15)
    raise TimeoutError("Timed out waiting for certificate to be issued")

def get_distribution_by_cname(cname):
    """Find a CloudFront distribution by its CNAME."""
    paginator = cloudfront.get_paginator('list_distributions')
    for page in paginator.paginate():
        for dist in page.get('DistributionList', {}).get('Items', []):
            if cname in dist.get('Aliases', {}).get('Items', []):
                return dist
    return None

def create_cloudfront_distribution(cert_arn):
    """Create a CloudFront distribution if it doesn't exist."""
    existing_dist = get_distribution_by_cname(DOMAIN_NAME)
    if existing_dist:
        print(f"Found existing CloudFront distribution: {existing_dist['Id']}")
        return existing_dist['Id'], existing_dist['DomainName']

    print("Creating CloudFront distribution...")
    
    # Create Origin Access Identity
    oai_res = cloudfront.create_cloud_front_origin_access_identity(
        CloudFrontOriginAccessIdentityConfig={
            'CallerReference': f'oai-{DOMAIN_NAME}-{time.time()}',
            'Comment': f'OAI for {DOMAIN_NAME}'
        }
    )
    oai_id = oai_res['CloudFrontOriginAccessIdentity']['Id']
    oai_s3_canonical_user_id = oai_res['CloudFrontOriginAccessIdentity']['S3CanonicalUserId']
    print(f"Created Origin Access Identity: {oai_id}")

    # Update bucket policy to allow OAI access
    policy = json.loads(s3.get_bucket_policy(Bucket=BUCKET_NAME)['Policy'])
    policy['Statement'].append({
        "Sid": "AllowCloudFrontServicePrincipal",
        "Effect": "Allow",
        "Principal": {
            "CanonicalUser": oai_s3_canonical_user_id
        },
        "Action": "s3:GetObject",
        "Resource": f"arn:aws:s3:::{BUCKET_NAME}/*"
    })
    s3.put_bucket_policy(Bucket=BUCKET_NAME, Policy=json.dumps(policy))
    print("Updated bucket policy to allow CloudFront access.")

    distribution_config = {
        'CallerReference': f'dist-{DOMAIN_NAME}-{time.time()}',
        'Comment': f'Distribution for {DOMAIN_NAME}',
        'Enabled': True,
        'DefaultRootObject': 'index.html',
        'Origins': {
            'Quantity': 1,
            'Items': [{
                'Id': f'S3-{BUCKET_NAME}',
                'DomainName': f'{BUCKET_NAME}.s3.amazonaws.com',
                'S3OriginConfig': {
                    'OriginAccessIdentity': f'origin-access-identity/cloudfront/{oai_id}'
                }
            }]
        },
        'DefaultCacheBehavior': {
            'TargetOriginId': f'S3-{BUCKET_NAME}',
            'ForwardedValues': {
                'QueryString': False,
                'Cookies': {'Forward': 'none'},
                'Headers': {'Quantity': 1, 'Items': ['Origin']}
            },
            'ViewerProtocolPolicy': 'redirect-to-https',
            'MinTTL': 0,
            'AllowedMethods': {
                'Quantity': 2,
                'Items': ['GET', 'HEAD']
            },
            'SmoothStreaming': False,
            'DefaultTTL': 86400,
            'MaxTTL': 31536000,
            'TrustedSigners': {'Enabled': False, 'Quantity': 0},
        },
        'Aliases': {
            'Quantity': 1,
            'Items': [DOMAIN_NAME]
        },
        'ViewerCertificate': {
            'ACMCertificateArn': cert_arn,
            'SSLSupportMethod': 'sni-only',
            'MinimumProtocolVersion': 'TLSv1.2_2021'
        }
    }

    res = cloudfront.create_distribution(DistributionConfig=distribution_config)
    print("CloudFront distribution created successfully.")
    print(f"Distribution ID: {res['Distribution']['Id']}")
    print(f"Distribution Domain: {res['Distribution']['DomainName']}")
    return res['Distribution']['Id'], res['Distribution']['DomainName']

def configure_route53(dist_domain, dist_id, zone_id):
    """Configure Route 53 to point to the CloudFront distribution."""
    print(f"Upserting 'A' record for {DOMAIN_NAME} in zone {zone_id}...")
    try:
        route53.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                'Changes': [{
                    'Action': 'UPSERT',
                    'ResourceRecordSet': {
                        'Name': DOMAIN_NAME,
                        'Type': 'A',
                        'AliasTarget': {
                            'HostedZoneId': 'Z2FDTNDATAQYW2',  # This is the default CloudFront hosted zone ID
                            'DNSName': dist_domain,
                            'EvaluateTargetHealth': False
                        }
                    }
                }]
            }
        )
        print("Route 53 configuration complete.")
    except ClientError as e:
        print(f"Error configuring Route 53: {e}")

def find_distribution_id_for_bucket(bucket_name):
    """Find the CloudFront distribution ID associated with an S3 bucket."""
    try:
        distributions = cloudfront.list_distributions()
        for dist in distributions.get('DistributionList', {}).get('Items', []):
            for origin in dist.get('Origins', {}).get('Items', []):
                if bucket_name in origin.get('DomainName', ''):
                    return dist['Id']
    except ClientError as e:
        print(f"Error finding distribution: {e}")
    return None

def find_or_create_hosted_zone(domain_name):
    """Find a Route 53 hosted zone by domain name, or create it if it doesn't exist."""
    try:
        zones = route53.list_hosted_zones_by_name(DNSName=domain_name)
        for zone in zones.get('HostedZones', []):
            if zone['Name'] == f"{domain_name}.":
                print(f"Found existing hosted zone: {zone['Id']}")
                return zone['Id']

        print(f"Hosted zone for {domain_name} not found. Creating it now...")
        response = route53.create_hosted_zone(
            Name=domain_name,
            CallerReference=f"create-zone-{time.time()}"
        )
        zone_id = response['HostedZone']['Id']
        print(f"Successfully created hosted zone: {zone_id}")
        print("If your domain was not purchased via Route 53, please ensure your registrar uses these Name Servers:")
        for ns in response['DelegationSet']['NameServers']:
            print(f"- {ns}")
        return zone_id
    except ClientError as e:
        print(f"Error finding or creating hosted zone: {e}")
        raise

def invalidate_cloudfront_cache(distribution_id, items=['/*']):
    """Create a CloudFront invalidation."""
    if not distribution_id:
        print("Could not find a distribution ID to invalidate.")
        return
    
    print(f"Creating invalidation for distribution: {distribution_id}")
    try:
        cloudfront.create_invalidation(
            DistributionId=distribution_id,
            InvalidationBatch={
                'Paths': {
                    'Quantity': len(items),
                    'Items': items
                },
                'CallerReference': f'invalidation-{time.time()}'
            }
        )
        print("Invalidation created successfully. Please allow a few minutes for it to propagate.")
    except ClientError as e:
        print(f"Error creating invalidation: {e}")

def main():
    parser = argparse.ArgumentParser(description="Setup S3/CloudFront and optionally invalidate the cache.")
    parser.add_argument('--invalidate', action='store_true', help='Invalidate the CloudFront cache for the website.')
    args = parser.parse_args()

    if args.invalidate:
        dist_id = find_distribution_id_for_bucket(BUCKET_NAME)
        invalidate_cloudfront_cache(dist_id)
    else:
        zone_id = find_or_create_hosted_zone(DOMAIN_NAME)
        if not zone_id:
            return # Stop if we couldn't get a zone ID

        create_s3_bucket()
        cert_arn = get_acm_certificate_arn()
        
        if cert_arn:
            create_dns_validation_record(cert_arn, zone_id)
            wait_for_certificate_issued(cert_arn)
            dist_id, dist_domain = create_cloudfront_distribution(cert_arn)
            configure_route53(dist_domain, dist_id, zone_id)

if __name__ == "__main__":
    main()