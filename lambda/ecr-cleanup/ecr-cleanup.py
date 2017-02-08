import boto3, json, datetime, time

"""
describes all repositories, grabs a list of images according to tag
deletes this if they are outside the retention period (specified by
the : if (now - date_time) > datetime.timedelta(weeks=2) in the
ListOldImages function.  The lambda returns an array containing the
deleted images
"""

class CleanupECR(object):

    def __init__(self, aws_id):
        self.client = boto3.client('ecr')
        self.aws_id = aws_id
        repos = self.client.describe_repositories(registryId=self.aws_id)
        self.repo_list = [i['repositoryName'] for i in repos['repositories']]
        self.images = []
        self.old_images = []
        self.untagged_images = []
        self.deleteItems = {}

    def BatchGetImages(self):
        for repo in self.repo_list:
            list_images = self.client.list_images(registryId=self.aws_id, repositoryName=repo)
            image_list = [i for i in list_images['imageIds']]
            image_batch_list = self.client.batch_get_image(registryId=self.aws_id, repositoryName=repo, imageIds=image_list)
            self.images.append((repo, image_batch_list))

    def ListOldImages(self):
        for i in self.images:
            for x in i[1]['images']:
                if 'imageTag' in x['imageId']:
                    imageTag = x['imageId']['imageTag']
                    if imageTag.startswith("latest"):
                        """
			add image tags to specify which
			images will be cleaned up.
			"""
                        manifest = json.loads(x['imageManifest'])
                        history = json.loads(manifest['history'][0]['v1Compatibility'])
                        time = history['created'][0:25]
                        date_time = datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S.%f")
                        now = datetime.datetime.utcnow()
                        if (now - date_time) > datetime.timedelta(weeks=2):
                            obj = (i[0], x['imageId'])
                            self.old_images.append(obj)
                    
    def ListUntaggedImages(self):
        for i in self.images:
            for x in i[1]['images']:
                if not 'imageTag' in x['imageId']:
                    obj = (i[0], x['imageId'])
                    self.untagged_images.append(obj)

    def SortByRepo(self):
        for i in self.repo_list:
            self.deleteItems[i] = []
        for i in self.old_images:
            if i[0] in self.deleteItems.keys():
                self.deleteItems[i[0]].append(i[1])
        for i in self.untagged_images:
            if i[0] in self.deleteItems.keys():
                self.deleteItems[i[0]].append(i[1])

    def DeleteImages(self):
        self.deleted = []
        for i in self.deleteItems:
            if not self.deleteItems[i]:
                pass
            else:
                obj = self.client.batch_delete_image(registryId=self.aws_id, repositoryName=i, imageIds=self.deleteItems[i])
                self.deleted.append(obj)

def lambda_handler(event, context):
    cleanup = CleanupECR(event['aws_id'])
    cleanup.BatchGetImages()
    cleanup.ListOldImages()
    cleanup.ListUntaggedImages()
    cleanup.SortByRepo()
    cleanup.DeleteImages()
    response = cleanup.deleted
    return response
