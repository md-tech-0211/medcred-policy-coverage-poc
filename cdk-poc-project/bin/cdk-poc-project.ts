#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { AIPOCStack } from '../lib/AIPOCStack';

const app = new cdk.App();

new AIPOCStack(app, 'AIPOCStack', {
  env: { 
    account: process.env.CDK_DEFAULT_ACCOUNT, 
    region: 'us-east-1'
  },
});