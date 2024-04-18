docker build --pull --rm -f "Dockerfile.sender" -t sender:latest "."
docker tag sender:latest cr.yandex/crp8ek2lo6uuvnveblac/sender
docker push cr.yandex/crp8ek2lo6uuvnveblac/sender
yc serverless container revision deploy ^
--container-name sender --image cr.yandex/crp8ek2lo6uuvnveblac/sender ^
--cores 1 --core-fraction 5 --memory 256MB --concurrency 1 ^
--execution-timeout 300s --service-account-id ajeeqpdslsj7pt0usup8
