// Preserved original production function from audio/voice source 00136ecc93.
glm::vec2 TouchscreenVirtualPadDevice::clippedPointInCircle(float radius, glm::vec2 origin, glm::vec2 touchPoint) {
    float deltaX = touchPoint.x - origin.x;
    float deltaY = touchPoint.y - origin.y;

    float distance = sqrt(pow(deltaX, 2) + pow(deltaY, 2));

    // First case, inside the boundaires, just use the distance
    if (distance <= radius) {
        return touchPoint;
    }

    // Second case, purely vertical (avoid division by zero)
    if (deltaX == 0.0f) {
        return vec2(touchPoint.x, clip(touchPoint.y, origin.y-radius, origin.y+radius) );
    }

    // Third case, calculate point in circumference
    // line formula
    float m = deltaY / deltaX;
    float b = touchPoint.y - m * touchPoint.x;

    // quadtratic coefs of circumference and line intersection
    float qa = powf(m, 2.0f) + 1.0f;
    float qb = 2.0f * ( m * b - origin.x - origin.y * m);
    float qc = powf(origin.x, 2.0f) - powf(radius, 2.0f) + b * b - 2.0f * b * origin.y + powf(origin.y, 2.0f);

    float discr = qb * qb - 4.0f * qa * qc;
    float discrSign = deltaX > 0.0f ? 1.0f : - 1.0f;

    float finalX = (-qb + discrSign * sqrtf(discr)) / (2.0f * qa);
    float finalY = m * finalX + b;

    return vec2(finalX, finalY);
}
