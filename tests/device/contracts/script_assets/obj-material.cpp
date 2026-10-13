// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include "obj-material-services.h"
#include <cstdio>
Q_LOGGING_CATEGORY(modelformat,"test.obj-material")
#include "obj-body.inc"
static void write(const QString& filename,const QByteArray& bytes){
    QDir().mkpath(QFileInfo(filename).absolutePath());QFile file(filename);assert(file.open(QFile::WriteOnly));assert(file.write(bytes)==bytes.size());
}
static HFMModel::Pointer parse(const QByteArray& data,const QUrl& url){
    OBJSerializer serializer;auto model=serializer.read(data,{{"combineParts",true}},url);
    assert(model&&model->meshes.size()==1&&model->meshes[0].vertices.size()==3);
    assert(model->meshes[0].parts.size()==1&&model->meshes[0].parts[0].triangleIndices.size()==3);
    return model;
}

int main(int argc,char**argv){
    QCoreApplication application(argc,argv);QTemporaryDir folder;auto* provider=DependencyManager::get<ResourceManager>();provider->root=folder.path();
    const QByteArray geometry="v 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 0 1\nusemtl triangle\nf 1/1 2/2 3/3\n";
    write(folder.path()+"/project/nested/material.mtl","newmtl triangle\nKd 0.2 0.4 0.6\nmap_Kd textures/image.png\nmap_Ke ../shared/image.png\nmap_Ks textures/image.png\nmap_bump -bm 0.7 textures/image.png\nmap_d textures/image.png\n");
    QImage image(2,2,QImage::Format_RGBA8888);image.fill(QColor(30,100,200));
    QDir().mkpath(folder.path()+"/project/nested/textures");assert(image.save(folder.path()+"/project/nested/textures/image.png"));
    auto serializer=parse("mtllib nested/material.mtl\n"+geometry,QUrl("atp:/project/scene.obj"));
    assert(provider->requested==QList<QUrl>{QUrl("atp:/project/nested/material.mtl")});
    const auto material=serializer->materials.value("triangle");
    assert(material.diffuseColor==glm::vec3(0.2f,0.4f,0.6f));
    assert(material.albedoTexture.filename=="nested/textures/image.png");
    assert(material.emissiveTexture.filename=="shared/image.png");
    assert(material.specularTexture.filename==material.albedoTexture.filename);
    assert(material.normalTexture.filename==material.albedoTexture.filename&&material.bumpMultiplier==0.7f);
    assert(material.opacityTexture.filename==material.albedoTexture.filename);
    auto texture=NetworkMaterial::getTextureUrl(QUrl("atp:/project/"),material.albedoTexture);
    assert(texture==QUrl("atp:/project/nested/textures/image.png"));const auto resource=requestData(texture);
    QImage decoded;assert(std::get<0>(resource)&&decoded.loadFromData(std::get<1>(resource))&&decoded.convertToFormat(image.format())==image);
    provider->requested.clear();
    auto local=parse("mtllib nested/material.mtl\n"+geometry,QUrl::fromLocalFile(folder.path()+"/project/scene.obj"));
    assert(NetworkMaterial::getTextureUrl(QUrl::fromLocalFile(folder.path()+"/project/"),local->materials.value("triangle").albedoTexture)==QUrl::fromLocalFile(folder.path()+"/project/nested/textures/image.png"));
    write(folder.path()+"/project/material.mtl","newmtl triangle\nmap_Kd fallback.png\n");provider->requested.clear();
    auto fallback=parse("mtllib vanished/material.mtl\n"+geometry,QUrl("atp:/project/scene.obj"));
    assert((provider->requested==QList<QUrl>{QUrl("atp:/project/vanished/material.mtl"),QUrl("atp:/project/material.mtl")}));
    assert(fallback->materials.value("triangle").albedoTexture.filename=="fallback.png");
    provider->requested.clear();
    auto missing=parse("mtllib missing.mtl\n"+geometry,QUrl("atp:/project/scene.obj"));
    assert(provider->requested.size()==1&&missing->materials.value("triangle").albedoTexture.filename.isEmpty());
    auto windows=parse("mtllib nested\\material.mtl\n"+geometry,QUrl("atp:/project/scene.obj"));
    assert(windows->materials.value("triangle").albedoTexture.filename=="nested/textures/image.png");
    // The real consumer applies an explicit FST texdir/textureBaseURL to relative HFM filenames.
    assert(NetworkMaterial::getTextureUrl(QUrl("atp:/override/"),material.albedoTexture)==QUrl("atp:/override/nested/textures/image.png"));
    assert(NetworkMaterial::getTextureUrl(QUrl("https://assets.invalid/override/"),material.albedoTexture)==QUrl("https://assets.invalid/override/nested/textures/image.png"));
    write(folder.path()+"/project/absolute.mtl","newmtl triangle\nmap_Kd https://external.invalid/image.png\n");
    auto external=parse("mtllib absolute.mtl\n"+geometry,QUrl("atp:/project/scene.obj"));
    assert(NetworkMaterial::getTextureUrl(QUrl("atp:/override/"),external->materials["triangle"].albedoTexture)==QUrl("https://external.invalid/image.png"));
    auto externalLibrary=parse("mtllib atp:/project/nested/material.mtl\n"+geometry,QUrl("atp:/project/scene.obj"));
    assert(NetworkMaterial::getTextureUrl(QUrl("atp:/override/"),externalLibrary->materials["triangle"].albedoTexture)==QUrl("atp:/project/nested/textures/image.png"));
    // Two MTLs can both name image.png; each generated HFM texture must retain its own base.
    write(folder.path()+"/project/second/material.mtl","newmtl other\nmap_Kd image.png\n");
    QImage secondImage(2,2,QImage::Format_RGBA8888);secondImage.fill(QColor(220,10,20));assert(secondImage.save(folder.path()+"/project/second/image.png"));
    OBJSerializer multiple;provider->requested.clear();
    auto combined=multiple.read("mtllib nested/material.mtl\nmtllib second/material.mtl\n"+geometry+"usemtl other\nf 1/1 2/2 3/3\n",{{"combineParts",true}},QUrl("atp:/project/scene.obj"));
    assert(combined&&combined->meshes[0].vertices.size()==6&&combined->meshes[0].parts.size()==2);
    assert(provider->requested.size()==2&&provider->requested.contains(QUrl("atp:/project/second/material.mtl")));
    auto secondTexture=NetworkMaterial::getTextureUrl(QUrl("atp:/project/"),combined->materials["other"].albedoTexture);
    assert(secondTexture==QUrl("atp:/project/second/image.png"));
    const auto secondData=requestData(secondTexture);QImage decodedSecond;
    assert(std::get<0>(secondData)&&decodedSecond.loadFromData(std::get<1>(secondData))&&decodedSecond.pixelColor(0,0)==QColor(220,10,20));
    std::puts("PASS actual OBJ/MTL parsers and resource requests: ATP/local hierarchy, all texture kinds, image bytes, fallback and missing library");
}
