// SPDX-License-Identifier: Apache-2.0
// Authored real FBX floor with an external texture dependency.
export const modelFloorFbx=`; FBX 7.4.0 project file
FBXHeaderExtension:  {
\tFBXVersion: 7400
}
Objects:  {
\tGeometry: 201, "Geometry::Floor", "Mesh" {
\t\tVertices: *9 {
\t\t\ta: 0,0,0,10,0,0,0,0,10
\t\t}
\t\tPolygonVertexIndex: *3 {
\t\t\ta: 0,2,-2
\t\t}
\t}
\tModel: 401, "Model::Floor", "Mesh" {
\t}
\tMaterial: 101, "Material::Floor", "" {
\t\tShadingModel: "phong"
\t}
\tVideo: 501, "Video::Floor", "Clip" {
\t\tRelativeFilename: "floor.png"
\t\tFilename: "floor.png"
\t}
\tTexture: 301, "Texture::Floor", "TextureVideoClip" {
\t\tRelativeFilename: "floor.png"
\t\tFileName: "floor.png"
\t}
}
Connections:  {
\tC: "OO",201,401
\tC: "OO",101,401
\tC: "OO",401,0
\tC: "OP",301,101,"DiffuseColor"
\tC: "OO",501,301
}
`;
